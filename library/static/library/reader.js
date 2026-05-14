(function () {
    function blockEvent(event) {
        event.preventDefault();
        event.stopPropagation();
        return false;
    }

    document.addEventListener("contextmenu", blockEvent);
    document.addEventListener("dragstart", blockEvent);
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
        controlsLocked: true,
        observer: null,
        renderingPages: {},
        scrollFrame: null,
        resizeTimer: null
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
        searchPage: document.getElementById("search-page")
    };

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

    function shellContentWidth() {
        return Math.max(260, els.canvasShell.clientWidth - 52);
    }

    function scaleForPage(page) {
        var viewport = page.getViewport({ scale: 1 });
        if (!state.fitWidth) {
            return 1;
        }
        return Math.min(2.25, shellContentWidth() / viewport.width);
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
            var canvas = surface.querySelector("canvas");

            if (!canvas) {
                canvas = document.createElement("canvas");
                surface.innerHTML = "";
                surface.appendChild(canvas);
            }

            var context = canvas.getContext("2d", { alpha: false });
            canvas.width = Math.floor(viewport.width * outputScale);
            canvas.height = Math.floor(viewport.height * outputScale);
            canvas.style.width = Math.floor(viewport.width) + "px";
            canvas.style.height = Math.floor(viewport.height) + "px";
            shell.style.width = Math.floor(viewport.width) + "px";
            shell.style.minHeight = Math.floor(viewport.height) + "px";

            return page.render({
                canvasContext: context,
                viewport: viewport,
                transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null
            }).promise;
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

    function enterFullscreen() {
        if (!document.fullscreenElement) {
            app.requestFullscreen();
        }
    }

    function exitFullscreen() {
        if (document.fullscreenElement) {
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
            setLoading("Could not load this PDF.");
        });
    }

    els.firstPage.addEventListener("click", function () { scrollToPage(1); });
    els.prevPage.addEventListener("click", function () { scrollToPage(state.pageNumber - 1); });
    els.nextPage.addEventListener("click", function () { scrollToPage(state.pageNumber + 1); });
    els.lastPage.addEventListener("click", function () { scrollToPage(state.totalPages); });
    els.fullscreen.addEventListener("click", enterFullscreen);
    els.exitFullscreen.addEventListener("click", exitFullscreen);
    els.fitWidth.addEventListener("click", function () {
        state.fitWidth = true;
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
    document.addEventListener("keydown", function (event) {
        var targetName = String(event.target.tagName || "").toLowerCase();
        if (targetName === "input" || targetName === "select" || targetName === "textarea") {
            return;
        }

        if (event.key === "ArrowDown" || event.key === "PageDown") {
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

    setControlsDisabled(true);
    loadPdf();
})();
