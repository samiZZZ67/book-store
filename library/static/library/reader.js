(function () {
    function blockEvent(event) {
        event.preventDefault();
        event.stopPropagation();
        return false;
    }

    document.addEventListener("keydown", function (event) {
        var key = String(event.key || "").toLowerCase();
        if ((event.ctrlKey || event.metaKey) && (key === "s" || key === "p")) {
            blockEvent(event);
        }
    });
    window.addEventListener("beforeprint", blockEvent);

    var app = document.getElementById("reader-app");
    if (!app) {
        return;
    }

    var pdfjsLib = window.pdfjsLib;
    var state = {
        pdf: null,
        pageNumber: 1,
        totalPages: 0,
        fitWidth: true,
        readerZoom: 1,
        minReaderZoom: 1,
        maxReaderZoom: 3,
        controlsLocked: true,
        controlsOpen: false,
        immersive: false,
        observer: null,
        renderingPages: {},
        scrollFrame: null,
        resizeTimer: null,
        pinch: {
            active: false,
            startDistance: 0,
            startZoom: 1,
            previewZoom: 1,
            centerX: 0,
            centerY: 0
        },
        pan: {
            tracking: false,
            active: false,
            startX: 0,
            startY: 0,
            startScrollLeft: 0,
            startScrollTop: 0,
            startTime: 0,
            startOnText: false
        }
    };

    var els = {
        canvasShell: document.getElementById("canvas-shell"),
        pages: document.getElementById("pdf-pages"),
        loading: document.getElementById("reader-loading"),
        pageStatus: document.getElementById("page-status"),
        pageNumber: document.getElementById("page-number"),
        pageCount: document.getElementById("page-count"),
        firstPage: document.getElementById("first-page"),
        prevPage: document.getElementById("prev-page"),
        nextPage: document.getElementById("next-page"),
        lastPage: document.getElementById("last-page"),
        fullscreen: document.getElementById("fullscreen-btn"),
        exitFullscreen: document.getElementById("exit-fullscreen-btn"),
        fitWidth: document.getElementById("fit-width"),
        searchPage: document.getElementById("search-page"),
        controlsPanel: document.getElementById("reader-controls-panel"),
        controlsToggle: document.getElementById("reader-controls-toggle")
    };
    var compactReaderQuery = window.matchMedia ? window.matchMedia("(max-width: 640px)") : null;

    function setLoading(message) {
        els.loading.textContent = message;
        els.loading.hidden = !message;
    }

    function clampPage(pageNumber) {
        return Math.max(1, Math.min(state.totalPages || 1, Number(pageNumber) || 1));
    }

    function pageShell(pageNumber) {
        return els.pages.querySelector('[data-page-number="' + pageNumber + '"]');
    }

    function updateStatus() {
        var hasPdf = Boolean(state.pdf && state.totalPages);
        var controlsDisabled = state.controlsLocked || !hasPdf;
        var onFirstPage = state.pageNumber <= 1;
        var onLastPage = state.pageNumber >= state.totalPages;

        els.pageStatus.textContent = hasPdf
            ? "Page " + state.pageNumber + " of " + state.totalPages
            : "Loading";
        els.pageNumber.value = state.pageNumber;
        els.pageNumber.max = state.totalPages || 1;
        els.pageCount.textContent = "/ " + (state.totalPages || 0);

        els.firstPage.disabled = controlsDisabled || onFirstPage;
        els.prevPage.disabled = controlsDisabled || onFirstPage;
        els.nextPage.disabled = controlsDisabled || onLastPage;
        els.lastPage.disabled = controlsDisabled || onLastPage;
        els.fullscreen.disabled = controlsDisabled;
        els.exitFullscreen.disabled = controlsDisabled;
        els.fitWidth.disabled = controlsDisabled;
        els.searchPage.disabled = controlsDisabled;
        els.pageNumber.disabled = controlsDisabled;
        els.fitWidth.classList.toggle("is-active", state.fitWidth);
    }

    function setControlsDisabled(disabled) {
        state.controlsLocked = disabled;
        updateStatus();
    }

    function isCompactReader() {
        return Boolean(compactReaderQuery && compactReaderQuery.matches);
    }

    function clampValue(value, min, max) {
        return Math.max(min, Math.min(max, Number(value) || min));
    }

    function activeReaderZoom() {
        return state.immersive ? state.readerZoom : 1;
    }

    function isZoomedReader() {
        return activeReaderZoom() > 1.01;
    }

    function canUseTouchZoom() {
        return Boolean(state.pdf && state.immersive);
    }

    function shellContentWidth() {
        var styles = window.getComputedStyle ? window.getComputedStyle(els.canvasShell) : null;
        var horizontalPadding = 0;
        var edgeGap = isCompactReader() ? 4 : 16;

        if (styles) {
            horizontalPadding = (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0);
        }

        return Math.max(260, els.canvasShell.clientWidth - horizontalPadding - edgeGap);
    }

    function updateReaderChrome() {
        var floatingControls = state.immersive || isCompactReader();
        var controlsOpen = floatingControls && state.controlsOpen;

        app.classList.toggle("is-immersive", state.immersive);
        app.classList.toggle("is-compact-reader", isCompactReader());
        app.classList.toggle("is-controls-open", controlsOpen);
        app.classList.toggle("is-reader-zoomed", isZoomedReader());
        document.body.classList.toggle("reader-immersive-lock", state.immersive);

        if (els.controlsToggle) {
            els.controlsToggle.hidden = !floatingControls;
            els.controlsToggle.textContent = controlsOpen ? "Hide" : "Menu";
            els.controlsToggle.setAttribute("aria-expanded", controlsOpen ? "true" : "false");
        }
    }

    function setControlsOpen(open) {
        state.controlsOpen = Boolean(open);
        updateReaderChrome();
    }

    function resetTouchGestureState() {
        state.pinch.active = false;
        state.pan.tracking = false;
        state.pan.active = false;
        app.classList.remove("is-touch-zooming");
        app.classList.remove("is-reader-panning");
        els.pages.style.removeProperty("--reader-pinch-scale");
        els.pages.style.removeProperty("--reader-pinch-origin-x");
        els.pages.style.removeProperty("--reader-pinch-origin-y");
    }

    function refreshReaderLayout() {
        window.clearTimeout(state.resizeTimer);
        state.resizeTimer = window.setTimeout(function () {
            if (state.pdf && state.fitWidth) {
                state.pdf.getPage(1).then(setEstimatedPageSize).then(rerenderVisiblePages);
            }
        }, 180);
    }

    function setImmersiveMode(enabled) {
        state.immersive = Boolean(enabled);
        if (state.immersive) {
            state.controlsOpen = false;
        }
        resetTouchGestureState();
        updateReaderChrome();
        if (!state.immersive && state.readerZoom !== 1) {
            applyReaderZoom(1, null, false);
        }
        refreshReaderLayout();
    }

    function scaleForPage(page) {
        var viewport = page.getViewport({ scale: 1 });
        var baseScale;
        if (!state.fitWidth) {
            baseScale = 1;
        } else {
            baseScale = Math.min(2.25, shellContentWidth() / viewport.width);
        }

        return Math.min(4.5, baseScale * activeReaderZoom());
    }

    function setEstimatedPageSize(page) {
        var scale = scaleForPage(page);
        var viewport = page.getViewport({ scale: scale });
        els.pages.style.setProperty("--pdf-page-width", Math.floor(viewport.width) + "px");
        els.pages.style.setProperty("--pdf-page-height", Math.floor(viewport.height) + "px");
    }

    function buildPageShells() {
        var fragment = document.createDocumentFragment();
        var pageNumber;

        els.pages.innerHTML = "";
        for (pageNumber = 1; pageNumber <= state.totalPages; pageNumber += 1) {
            var shell = document.createElement("article");
            shell.className = "pdf-page-shell";
            shell.dataset.pageNumber = String(pageNumber);
            shell.dataset.rendered = "0";
            shell.innerHTML = [
                '<div class="pdf-page-label">Page ' + pageNumber + '</div>',
                '<div class="pdf-page-surface">',
                '<span class="pdf-page-loading">Waiting...</span>',
                "</div>"
            ].join("");
            fragment.appendChild(shell);
        }

        els.pages.appendChild(fragment);
    }

    function renderPage(pageNumber, force) {
        pageNumber = clampPage(pageNumber);

        if (!state.pdf) {
            return Promise.resolve();
        }

        var shell = pageShell(pageNumber);
        if (!shell) {
            return Promise.resolve();
        }

        if (!force && shell.dataset.rendered === "1") {
            return Promise.resolve();
        }

        if (state.renderingPages[pageNumber]) {
            if (force) {
                shell.dataset.needsRerender = "1";
            }
            return state.renderingPages[pageNumber];
        }

        shell.classList.add("is-rendering");
        shell.classList.remove("has-error");
        var loadingLabel = shell.querySelector(".pdf-page-loading");
        if (loadingLabel) {
            loadingLabel.textContent = "Rendering...";
        }

        state.renderingPages[pageNumber] = state.pdf.getPage(pageNumber).then(function (page) {
            var scale = scaleForPage(page);
            var viewport = page.getViewport({ scale: scale });
            var outputScale = Math.min(window.devicePixelRatio || 1, 2);
            var surface = shell.querySelector(".pdf-page-surface");
            var stack = surface.querySelector(".pdf-page-stack");
            var canvas = surface.querySelector("canvas");
            var textLayer = surface.querySelector(".textLayer");

            if (!stack) {
                stack = document.createElement("div");
                stack.className = "pdf-page-stack";
                canvas = document.createElement("canvas");
                textLayer = document.createElement("div");
                textLayer.className = "textLayer";
                textLayer.setAttribute("aria-hidden", "true");
                surface.innerHTML = "";
                stack.appendChild(canvas);
                stack.appendChild(textLayer);
                surface.appendChild(stack);
            }
            if (!textLayer) {
                textLayer = document.createElement("div");
                textLayer.className = "textLayer";
                textLayer.setAttribute("aria-hidden", "true");
                stack.appendChild(textLayer);
            }

            var context = canvas.getContext("2d", { alpha: false });
            canvas.width = Math.floor(viewport.width * outputScale);
            canvas.height = Math.floor(viewport.height * outputScale);
            canvas.style.width = Math.floor(viewport.width) + "px";
            canvas.style.height = Math.floor(viewport.height) + "px";
            stack.style.width = Math.floor(viewport.width) + "px";
            stack.style.height = Math.floor(viewport.height) + "px";
            textLayer.style.width = Math.floor(viewport.width) + "px";
            textLayer.style.height = Math.floor(viewport.height) + "px";
            textLayer.innerHTML = "";
            shell.style.width = Math.floor(viewport.width) + "px";
            shell.style.minHeight = Math.floor(viewport.height) + "px";

            return page.render({
                canvasContext: context,
                viewport: viewport,
                transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null
            }).promise.then(function () {
                return renderTextLayer(page, viewport, textLayer);
            });
        }).then(function () {
            delete state.renderingPages[pageNumber];
            shell.dataset.rendered = "1";
            shell.classList.remove("is-rendering");

            if (shell.dataset.needsRerender === "1") {
                shell.dataset.needsRerender = "0";
                shell.dataset.rendered = "0";
                return renderPage(pageNumber, true);
            }

            return null;
        }).catch(function () {
            delete state.renderingPages[pageNumber];
            shell.classList.remove("is-rendering");
            shell.classList.add("has-error");
            shell.dataset.rendered = "0";

            var surface = shell.querySelector(".pdf-page-surface");
            surface.innerHTML = '<span class="pdf-page-loading">Could not render this page.</span>';
        });

        return state.renderingPages[pageNumber];
    }

    function fallbackTextLayer(textContent, viewport, container) {
        if (!pdfjsLib.Util || !pdfjsLib.Util.transform) {
            return;
        }

        textContent.items.forEach(function (item) {
            if (!item.str) {
                return;
            }

            var tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
            var fontHeight = Math.hypot(tx[2], tx[3]);
            var span = document.createElement("span");

            span.textContent = item.str;
            span.style.left = tx[4] + "px";
            span.style.top = (tx[5] - fontHeight) + "px";
            span.style.fontSize = fontHeight + "px";
            span.style.fontFamily = "sans-serif";
            span.style.transform = "rotate(" + Math.atan2(tx[1], tx[0]) + "rad)";
            container.appendChild(span);
        });
    }

    function renderTextLayer(page, viewport, container) {
        return page.getTextContent().then(function (textContent) {
            var renderTask;

            container.innerHTML = "";
            container.style.setProperty("--scale-factor", viewport.scale);

            if (pdfjsLib.renderTextLayer) {
                renderTask = pdfjsLib.renderTextLayer({
                    textContentSource: textContent,
                    container: container,
                    viewport: viewport,
                    textDivs: [],
                    enhanceTextSelection: true
                });

                if (renderTask && renderTask.promise) {
                    return renderTask.promise;
                }

                return renderTask || null;
            }

            fallbackTextLayer(textContent, viewport, container);
            return null;
        }).catch(function () {
            container.innerHTML = "";
        });
    }

    function renderNearby(pageNumber) {
        [pageNumber - 1, pageNumber, pageNumber + 1].forEach(function (nearbyPage) {
            if (nearbyPage >= 1 && nearbyPage <= state.totalPages) {
                renderPage(nearbyPage, false);
            }
        });
    }

    function renderVisiblePages() {
        var shellBounds = els.canvasShell.getBoundingClientRect();
        var preloadTop = shellBounds.top - 700;
        var preloadBottom = shellBounds.bottom + 700;

        els.pages.querySelectorAll(".pdf-page-shell").forEach(function (shell) {
            var bounds = shell.getBoundingClientRect();
            if (bounds.bottom >= preloadTop && bounds.top <= preloadBottom) {
                renderPage(Number(shell.dataset.pageNumber), false);
            }
        });
    }

    function currentPageFromScroll() {
        var shellBounds = els.canvasShell.getBoundingClientRect();
        var viewportMiddle = shellBounds.top + shellBounds.height / 2;
        var bestPage = state.pageNumber;
        var bestDistance = Infinity;

        els.pages.querySelectorAll(".pdf-page-shell").forEach(function (shell) {
            var bounds = shell.getBoundingClientRect();
            if (bounds.bottom < shellBounds.top || bounds.top > shellBounds.bottom) {
                return;
            }

            var pageMiddle = bounds.top + bounds.height / 2;
            var distance = Math.abs(pageMiddle - viewportMiddle);
            if (distance < bestDistance) {
                bestDistance = distance;
                bestPage = Number(shell.dataset.pageNumber);
            }
        });

        return clampPage(bestPage);
    }

    function handleScroll() {
        if (state.scrollFrame) {
            return;
        }

        state.scrollFrame = window.requestAnimationFrame(function () {
            state.scrollFrame = null;
            var nextPage = currentPageFromScroll();
            if (nextPage !== state.pageNumber) {
                state.pageNumber = nextPage;
                updateStatus();
                renderNearby(nextPage);
            }
            renderVisiblePages();
        });
    }

    function observePages() {
        if (!("IntersectionObserver" in window)) {
            renderVisiblePages();
            return;
        }

        if (state.observer) {
            state.observer.disconnect();
        }

        state.observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    renderPage(Number(entry.target.dataset.pageNumber), false);
                }
            });
        }, {
            root: els.canvasShell,
            rootMargin: "700px 0px",
            threshold: 0.01
        });

        els.pages.querySelectorAll(".pdf-page-shell").forEach(function (shell) {
            state.observer.observe(shell);
        });
    }

    function scrollToPage(pageNumber, smooth) {
        pageNumber = clampPage(pageNumber);
        var shell = pageShell(pageNumber);
        if (!shell) {
            return;
        }

        state.pageNumber = pageNumber;
        updateStatus();
        renderNearby(pageNumber);
        shell.scrollIntoView({
            behavior: smooth === false ? "auto" : "smooth",
            block: "start"
        });
    }

    function rerenderVisiblePages() {
        els.pages.querySelectorAll(".pdf-page-shell").forEach(function (shell) {
            if (shell.dataset.rendered === "1") {
                shell.dataset.rendered = "0";
            }
        });
        renderVisiblePages();
        renderNearby(state.pageNumber);
    }

    function applyReaderZoom(nextZoom, anchor, smooth) {
        var previousZoom = state.readerZoom;
        var shellRect = els.canvasShell.getBoundingClientRect();
        var anchorX = anchor ? anchor.clientX - shellRect.left : shellRect.width / 2;
        var anchorY = anchor ? anchor.clientY - shellRect.top : shellRect.height / 2;
        var contentX = els.canvasShell.scrollLeft + anchorX;
        var contentY = els.canvasShell.scrollTop + anchorY;
        var ratio;

        nextZoom = clampValue(nextZoom, state.minReaderZoom, state.maxReaderZoom);
        if (Math.abs(nextZoom - previousZoom) < 0.01) {
            state.readerZoom = nextZoom;
            updateReaderChrome();
            return;
        }

        state.readerZoom = nextZoom;
        ratio = state.readerZoom / previousZoom;
        updateReaderChrome();
        if (smooth !== false) {
            app.classList.add("is-reader-zoom-settling");
        }

        state.pdf.getPage(1).then(setEstimatedPageSize).then(function () {
            rerenderVisiblePages();
            window.requestAnimationFrame(function () {
                els.canvasShell.scrollLeft = Math.max(0, contentX * ratio - anchorX);
                els.canvasShell.scrollTop = Math.max(0, contentY * ratio - anchorY);
                handleScroll();
                window.setTimeout(function () {
                    app.classList.remove("is-reader-zoom-settling");
                    renderVisiblePages();
                }, 180);
            });
        });
    }

    function touchDistance(touchA, touchB) {
        return Math.hypot(touchA.clientX - touchB.clientX, touchA.clientY - touchB.clientY);
    }

    function touchCenter(touchA, touchB) {
        return {
            clientX: (touchA.clientX + touchB.clientX) / 2,
            clientY: (touchA.clientY + touchB.clientY) / 2
        };
    }

    function targetIsReaderChrome(target) {
        return Boolean(
            (els.controlsPanel && els.controlsPanel.contains(target)) ||
            (els.controlsToggle && els.controlsToggle.contains(target))
        );
    }

    function setPinchPreview(previewZoom) {
        var previewScale = previewZoom / state.pinch.startZoom;

        els.pages.style.setProperty("--reader-pinch-scale", previewScale.toFixed(4));
        app.classList.add("is-touch-zooming");
    }

    function startPinch(event) {
        var firstTouch = event.touches[0];
        var secondTouch = event.touches[1];
        var center = touchCenter(firstTouch, secondTouch);
        var pagesRect = els.pages.getBoundingClientRect();

        if (!canUseTouchZoom() || targetIsReaderChrome(event.target)) {
            return;
        }

        setControlsOpen(false);
        state.pinch.active = true;
        state.pinch.startDistance = Math.max(1, touchDistance(firstTouch, secondTouch));
        state.pinch.startZoom = state.readerZoom;
        state.pinch.previewZoom = state.readerZoom;
        state.pinch.centerX = center.clientX;
        state.pinch.centerY = center.clientY;
        state.pan.tracking = false;
        state.pan.active = false;

        els.pages.style.setProperty("--reader-pinch-origin-x", Math.max(0, center.clientX - pagesRect.left) + "px");
        els.pages.style.setProperty("--reader-pinch-origin-y", Math.max(0, center.clientY - pagesRect.top) + "px");
        setPinchPreview(state.readerZoom);
        event.preventDefault();
    }

    function updatePinch(event) {
        var firstTouch = event.touches[0];
        var secondTouch = event.touches[1];
        var center = touchCenter(firstTouch, secondTouch);
        var nextZoom;

        if (!state.pinch.active) {
            startPinch(event);
            return;
        }

        nextZoom = state.pinch.startZoom * (touchDistance(firstTouch, secondTouch) / state.pinch.startDistance);
        state.pinch.previewZoom = clampValue(nextZoom, state.minReaderZoom, state.maxReaderZoom);
        state.pinch.centerX = center.clientX;
        state.pinch.centerY = center.clientY;
        setPinchPreview(state.pinch.previewZoom);
        event.preventDefault();
    }

    function finishPinch(event) {
        var anchor;

        if (!state.pinch.active) {
            return;
        }

        anchor = {
            clientX: state.pinch.centerX,
            clientY: state.pinch.centerY
        };
        state.pinch.active = false;
        app.classList.remove("is-touch-zooming");
        els.pages.style.removeProperty("--reader-pinch-scale");
        els.pages.style.removeProperty("--reader-pinch-origin-x");
        els.pages.style.removeProperty("--reader-pinch-origin-y");
        applyReaderZoom(state.pinch.previewZoom, anchor, true);

        if (event) {
            event.preventDefault();
        }
    }

    function startPanTracking(event) {
        var touch = event.touches[0];

        if (!canUseTouchZoom() || !isZoomedReader() || targetIsReaderChrome(event.target)) {
            return;
        }

        state.pan.tracking = true;
        state.pan.active = false;
        state.pan.startX = touch.clientX;
        state.pan.startY = touch.clientY;
        state.pan.startScrollLeft = els.canvasShell.scrollLeft;
        state.pan.startScrollTop = els.canvasShell.scrollTop;
        state.pan.startTime = Date.now();
        state.pan.startOnText = Boolean(event.target.closest && event.target.closest(".textLayer span"));
    }

    function updatePan(event) {
        var touch = event.touches[0];
        var dx = touch.clientX - state.pan.startX;
        var dy = touch.clientY - state.pan.startY;
        var moved = Math.hypot(dx, dy);

        if (!state.pan.tracking || !touch) {
            return;
        }

        if (!state.pan.active) {
            if (moved < 7) {
                return;
            }
            if (state.pan.startOnText && Date.now() - state.pan.startTime > 220) {
                state.pan.tracking = false;
                return;
            }
            state.pan.active = true;
            setControlsOpen(false);
            app.classList.add("is-reader-panning");
        }

        event.preventDefault();
        els.canvasShell.scrollLeft = Math.max(0, state.pan.startScrollLeft - dx);
        els.canvasShell.scrollTop = Math.max(0, state.pan.startScrollTop - dy);
        handleScroll();
    }

    function finishPan() {
        state.pan.tracking = false;
        state.pan.active = false;
        app.classList.remove("is-reader-panning");
    }

    function handleReaderTouchStart(event) {
        if (!canUseTouchZoom()) {
            return;
        }

        if (event.touches.length >= 2) {
            startPinch(event);
            return;
        }

        if (event.touches.length === 1) {
            startPanTracking(event);
        }
    }

    function handleReaderTouchMove(event) {
        if (!canUseTouchZoom()) {
            return;
        }

        if (event.touches.length >= 2) {
            updatePinch(event);
            return;
        }

        if (state.pinch.active) {
            finishPinch(event);
            return;
        }

        if (event.touches.length === 1) {
            updatePan(event);
        }
    }

    function handleReaderTouchEnd(event) {
        if (state.pinch.active && (!event.touches || event.touches.length < 2)) {
            finishPinch(event);
        }

        if (!event.touches || event.touches.length === 0) {
            finishPan();
        }
    }

    function handleNativeGesture(event) {
        if (canUseTouchZoom() && !targetIsReaderChrome(event.target)) {
            event.preventDefault();
        }
    }

    function enterFullscreen() {
        setImmersiveMode(true);

        if (!document.fullscreenElement && app.requestFullscreen) {
            var request = app.requestFullscreen();
            if (request && request.catch) {
                request.catch(function () {
                    setImmersiveMode(true);
                });
            }
        }
    }

    function exitFullscreen() {
        setImmersiveMode(false);

        if (document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen();
        }
    }

    function loadPdf() {
        if (!pdfjsLib) {
            setLoading("PDF reader could not load.");
            return;
        }

        pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        setLoading("Loading PDF...");

        var loadingTask = pdfjsLib.getDocument({
            url: app.dataset.pdfUrl,
            rangeChunkSize: 65536
        });

        loadingTask.onProgress = function (progress) {
            if (progress.total) {
                var percent = Math.round((progress.loaded / progress.total) * 100);
                setLoading("Loading PDF... " + Math.min(percent, 100) + "%");
            } else {
                setLoading("Loading PDF...");
            }
        };

        loadingTask.promise.then(function (pdf) {
            state.pdf = pdf;
            state.totalPages = pdf.numPages;
            state.pageNumber = 1;
            buildPageShells();
            updateStatus();

            return pdf.getPage(1).then(function (page) {
                setEstimatedPageSize(page);
                setControlsDisabled(false);
                setLoading("Rendering first page...");
                return renderPage(1, true).then(observePages);
            });
        }).then(function () {
            setLoading("");
            scrollToPage(1, false);
            renderNearby(1);
        }).catch(function () {
            setControlsDisabled(true);
            showLoadError();
        });
    }

    function showLoadError() {
        setLoading("Could not load this PDF.");

        if (!window.fetch) {
            return;
        }

        fetch(app.dataset.pdfUrl, {
            credentials: "same-origin",
            cache: "no-store"
        }).then(function (response) {
            if (response.ok) {
                return "";
            }
            return response.text();
        }).then(function (message) {
            if (message) {
                setLoading(message.slice(0, 360));
            }
        }).catch(function () {
            setLoading("Could not load this PDF.");
        });
    }

    els.firstPage.addEventListener("click", function () { scrollToPage(1); });
    els.prevPage.addEventListener("click", function () { scrollToPage(state.pageNumber - 1); });
    els.nextPage.addEventListener("click", function () { scrollToPage(state.pageNumber + 1); });
    els.lastPage.addEventListener("click", function () { scrollToPage(state.totalPages); });
    els.fullscreen.addEventListener("click", enterFullscreen);
    els.exitFullscreen.addEventListener("click", exitFullscreen);
    if (els.controlsToggle) {
        els.controlsToggle.addEventListener("click", function () {
            setControlsOpen(!state.controlsOpen);
        });
    }
    els.fitWidth.addEventListener("click", function () {
        state.fitWidth = true;
        if (state.readerZoom !== 1) {
            applyReaderZoom(1, null, true);
        }
        updateStatus();
        rerenderVisiblePages();
    });
    els.searchPage.addEventListener("click", function () {
        scrollToPage(els.pageNumber.value);
    });
    els.pageNumber.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            scrollToPage(els.pageNumber.value);
        }
    });
    els.canvasShell.addEventListener("scroll", handleScroll, { passive: true });
    els.canvasShell.addEventListener("touchstart", handleReaderTouchStart, { passive: false });
    els.canvasShell.addEventListener("touchmove", handleReaderTouchMove, { passive: false });
    els.canvasShell.addEventListener("touchend", handleReaderTouchEnd, { passive: false });
    els.canvasShell.addEventListener("touchcancel", handleReaderTouchEnd, { passive: false });
    els.canvasShell.addEventListener("gesturestart", handleNativeGesture, { passive: false });
    els.canvasShell.addEventListener("gesturechange", handleNativeGesture, { passive: false });
    els.canvasShell.addEventListener("gestureend", handleNativeGesture, { passive: false });
    els.canvasShell.addEventListener("click", function () {
        if ((state.immersive || isCompactReader()) && state.controlsOpen) {
            setControlsOpen(false);
        }
    });
    document.addEventListener("keydown", function (event) {
        var targetName = String(event.target.tagName || "").toLowerCase();
        if (targetName === "input" || targetName === "select" || targetName === "textarea") {
            return;
        }

        if (event.key === "Escape" && state.immersive) {
            exitFullscreen();
        } else if (event.key === "ArrowDown" || event.key === "PageDown") {
            event.preventDefault();
            scrollToPage(state.pageNumber + 1);
        } else if (event.key === "ArrowUp" || event.key === "PageUp") {
            event.preventDefault();
            scrollToPage(state.pageNumber - 1);
        } else if (event.key === "Home") {
            event.preventDefault();
            scrollToPage(1);
        } else if (event.key === "End") {
            event.preventDefault();
            scrollToPage(state.totalPages);
        }
    });

    window.addEventListener("resize", function () {
        window.clearTimeout(state.resizeTimer);
        state.resizeTimer = window.setTimeout(function () {
            if (state.pdf && state.fitWidth) {
                state.pdf.getPage(1).then(setEstimatedPageSize).then(rerenderVisiblePages);
            }
        }, 160);
    });
    document.addEventListener("fullscreenchange", function () {
        if (document.fullscreenElement === app) {
            setImmersiveMode(true);
        } else if (!document.fullscreenElement && state.immersive) {
            setImmersiveMode(false);
        }
    });
    if (compactReaderQuery) {
        if (compactReaderQuery.addEventListener) {
            compactReaderQuery.addEventListener("change", function () {
                updateReaderChrome();
                refreshReaderLayout();
            });
        } else if (compactReaderQuery.addListener) {
            compactReaderQuery.addListener(function () {
                updateReaderChrome();
                refreshReaderLayout();
            });
        }
    }

    updateReaderChrome();
    setControlsDisabled(true);
    loadPdf();
})();
