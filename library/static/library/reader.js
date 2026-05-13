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
        var blocked = (event.ctrlKey || event.metaKey) && (key === "s" || key === "p");
        if (blocked) {
            blockEvent(event);
        }
    });

    window.addEventListener("beforeprint", blockEvent);

    var app = document.getElementById("reader-app");
    if (!app) {
        return;
    }

    var pdfjsLib = window.pdfjsLib;
    var loadingTask = null;
    var state = {
        pdf: null,
        pageNumber: 1,
        totalPages: 0,
        scale: 1,
        rotation: 0,
        fitMode: "",
        isRendering: false,
        pendingPage: null,
        searchQuery: "",
        searchResults: [],
        searchIndex: -1,
        textCache: {},
        startedAt: Date.now()
    };

    var els = {
        canvas: document.getElementById("pdf-canvas"),
        canvasShell: document.getElementById("canvas-shell"),
        loading: document.getElementById("reader-loading"),
        pageStatus: document.getElementById("page-status"),
        pageNumber: document.getElementById("page-number"),
        pageCount: document.getElementById("page-count"),
        progressFill: document.getElementById("progress-bar-fill"),
        timer: document.getElementById("read-timer"),
        pageList: document.getElementById("page-list"),
        sidebar: document.getElementById("page-sidebar"),
        sidebarToggle: document.getElementById("sidebar-toggle"),
        firstPage: document.getElementById("first-page"),
        prevPage: document.getElementById("prev-page"),
        nextPage: document.getElementById("next-page"),
        lastPage: document.getElementById("last-page"),
        zoomOut: document.getElementById("zoom-out"),
        zoomIn: document.getElementById("zoom-in"),
        zoomSelect: document.getElementById("zoom-select"),
        fitWidth: document.getElementById("fit-width"),
        fitPage: document.getElementById("fit-page"),
        rotateLeft: document.getElementById("rotate-left"),
        rotateRight: document.getElementById("rotate-right"),
        bookmark: document.getElementById("bookmark-page"),
        resume: document.getElementById("resume-page"),
        fullscreen: document.getElementById("fullscreen-btn"),
        searchInput: document.getElementById("search-input"),
        searchPrev: document.getElementById("search-prev"),
        searchNext: document.getElementById("search-next"),
        searchStatus: document.getElementById("search-status"),
        themeSelect: document.getElementById("theme-select")
    };
    var canvasContext = els.canvas.getContext("2d");
    var storagePrefix = "pdf-reader:" + app.dataset.bookId + ":";

    function setLoading(message) {
        els.loading.textContent = message;
        els.loading.hidden = !message;
    }

    function clampPage(pageNumber) {
        return Math.max(1, Math.min(state.totalPages || 1, Number(pageNumber) || 1));
    }

    function saveLastPage() {
        localStorage.setItem(storagePrefix + "last-page", String(state.pageNumber));
    }

    function savedPage(key) {
        var value = localStorage.getItem(storagePrefix + key);
        return value ? clampPage(value) : null;
    }

    function updateTimer() {
        var elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
        var minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
        var seconds = String(elapsed % 60).padStart(2, "0");
        els.timer.textContent = minutes + ":" + seconds;
    }

    function updateProgress() {
        var percent = state.totalPages ? Math.round((state.pageNumber / state.totalPages) * 100) : 0;
        els.pageStatus.textContent = "Page " + state.pageNumber + " of " + state.totalPages + " - " + percent + "%";
        els.pageNumber.value = state.pageNumber;
        els.pageCount.textContent = "/ " + state.totalPages;
        els.progressFill.style.width = percent + "%";
    }

    function updatePageList() {
        var buttons = els.pageList.querySelectorAll("button");
        buttons.forEach(function (button) {
            button.classList.toggle("active", Number(button.dataset.page) === state.pageNumber);
        });
    }

    function setControlsDisabled(disabled) {
        [
            els.firstPage,
            els.prevPage,
            els.nextPage,
            els.lastPage,
            els.zoomOut,
            els.zoomIn,
            els.fitWidth,
            els.fitPage,
            els.rotateLeft,
            els.rotateRight,
            els.bookmark,
            els.resume
        ].forEach(function (button) {
            button.disabled = disabled;
        });
        els.pageNumber.disabled = disabled;
    }

    function calculateFitScale(page) {
        if (!state.fitMode) {
            return state.scale;
        }

        var viewport = page.getViewport({ scale: 1, rotation: state.rotation });
        var shellWidth = Math.max(240, els.canvasShell.clientWidth - 32);
        var shellHeight = Math.max(240, els.canvasShell.clientHeight - 32);
        var widthScale = shellWidth / viewport.width;
        var pageScale = Math.min(widthScale, shellHeight / viewport.height);
        return state.fitMode === "width" ? widthScale : pageScale;
    }

    function renderPage(pageNumber) {
        if (!state.pdf) {
            return;
        }
        if (state.isRendering) {
            state.pendingPage = pageNumber;
            return;
        }

        state.isRendering = true;
        state.pageNumber = clampPage(pageNumber);
        setLoading("Rendering page...");
        setControlsDisabled(true);

        state.pdf.getPage(state.pageNumber).then(function (page) {
            var scale = calculateFitScale(page);
            var viewport = page.getViewport({ scale: scale, rotation: state.rotation });
            var outputScale = window.devicePixelRatio || 1;

            els.canvas.width = Math.floor(viewport.width * outputScale);
            els.canvas.height = Math.floor(viewport.height * outputScale);
            els.canvas.style.width = Math.floor(viewport.width) + "px";
            els.canvas.style.height = Math.floor(viewport.height) + "px";

            return page.render({
                canvasContext: canvasContext,
                viewport: viewport,
                transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null
            }).promise;
        }).then(function () {
            state.isRendering = false;
            setLoading("");
            setControlsDisabled(false);
            updateProgress();
            updatePageList();
            saveLastPage();

            if (state.pendingPage !== null) {
                var nextPage = state.pendingPage;
                state.pendingPage = null;
                renderPage(nextPage);
            }
        }).catch(function () {
            state.isRendering = false;
            setControlsDisabled(false);
            setLoading("Could not render this page.");
        });
    }

    function goToPage(pageNumber) {
        renderPage(clampPage(pageNumber));
    }

    function setScale(scale) {
        state.fitMode = "";
        state.scale = Math.max(0.35, Math.min(3, scale));
        els.zoomSelect.value = String(state.scale);
        renderPage(state.pageNumber);
    }

    function buildPageList() {
        els.pageList.textContent = "";
        for (var page = 1; page <= state.totalPages; page += 1) {
            var button = document.createElement("button");
            button.type = "button";
            button.textContent = "Page " + page;
            button.dataset.page = String(page);
            button.addEventListener("click", function (event) {
                goToPage(event.currentTarget.dataset.page);
            });
            els.pageList.appendChild(button);
        }
    }

    function getPageText(pageNumber) {
        if (state.textCache[pageNumber]) {
            return Promise.resolve(state.textCache[pageNumber]);
        }
        return state.pdf.getPage(pageNumber).then(function (page) {
            return page.getTextContent();
        }).then(function (textContent) {
            var text = textContent.items.map(function (item) {
                return item.str;
            }).join(" ").toLowerCase();
            state.textCache[pageNumber] = text;
            return text;
        });
    }

    function matchCount(text, query) {
        var count = 0;
        var index = text.indexOf(query);
        while (index !== -1) {
            count += 1;
            index = text.indexOf(query, index + query.length);
        }
        return count;
    }

    function updateSearchStatus(message) {
        if (message) {
            els.searchStatus.textContent = message;
            return;
        }
        if (!state.searchResults.length) {
            els.searchStatus.textContent = state.searchQuery ? "No matches" : "";
            return;
        }
        els.searchStatus.textContent = (state.searchIndex + 1) + " of " + state.searchResults.length;
    }

    function runSearch() {
        var query = els.searchInput.value.trim().toLowerCase();
        state.searchQuery = query;
        state.searchResults = [];
        state.searchIndex = -1;
        if (!query) {
            updateSearchStatus("");
            return;
        }

        updateSearchStatus("Searching...");
        var chain = Promise.resolve();
        for (var page = 1; page <= state.totalPages; page += 1) {
            (function (pageNumber) {
                chain = chain.then(function () {
                    return getPageText(pageNumber).then(function (text) {
                        var count = matchCount(text, query);
                        for (var index = 0; index < count; index += 1) {
                            state.searchResults.push({ page: pageNumber });
                        }
                    });
                });
            })(page);
        }

        chain.then(function () {
            if (state.searchResults.length) {
                state.searchIndex = 0;
                goToPage(state.searchResults[0].page);
            }
            updateSearchStatus("");
        }).catch(function () {
            updateSearchStatus("Search failed");
        });
    }

    function moveSearch(direction) {
        if (!state.searchResults.length) {
            runSearch();
            return;
        }
        state.searchIndex = (state.searchIndex + direction + state.searchResults.length) % state.searchResults.length;
        goToPage(state.searchResults[state.searchIndex].page);
        updateSearchStatus("");
    }

    function applyTheme(theme) {
        app.dataset.theme = theme;
        localStorage.setItem(storagePrefix + "theme", theme);
        els.themeSelect.value = theme;
    }

    function loadPdf() {
        if (!pdfjsLib) {
            setLoading("PDF reader could not load.");
            return;
        }

        pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        loadingTask = pdfjsLib.getDocument({ url: app.dataset.pdfUrl });
        setLoading("Loading PDF...");

        loadingTask.promise.then(function (pdf) {
            state.pdf = pdf;
            state.totalPages = pdf.numPages;
            buildPageList();
            updateProgress();
            applyTheme(localStorage.getItem(storagePrefix + "theme") || "light");
            renderPage(savedPage("last-page") || 1);
        }).catch(function () {
            setLoading("Could not load this PDF.");
        });
    }

    els.sidebarToggle.addEventListener("click", function () {
        els.sidebar.classList.toggle("collapsed");
    });
    els.firstPage.addEventListener("click", function () { goToPage(1); });
    els.prevPage.addEventListener("click", function () { goToPage(state.pageNumber - 1); });
    els.nextPage.addEventListener("click", function () { goToPage(state.pageNumber + 1); });
    els.lastPage.addEventListener("click", function () { goToPage(state.totalPages); });
    els.pageNumber.addEventListener("change", function () { goToPage(els.pageNumber.value); });
    els.zoomOut.addEventListener("click", function () { setScale(state.scale - 0.25); });
    els.zoomIn.addEventListener("click", function () { setScale(state.scale + 0.25); });
    els.zoomSelect.addEventListener("change", function () { setScale(Number(els.zoomSelect.value)); });
    els.fitWidth.addEventListener("click", function () {
        state.fitMode = "width";
        renderPage(state.pageNumber);
    });
    els.fitPage.addEventListener("click", function () {
        state.fitMode = "page";
        renderPage(state.pageNumber);
    });
    els.rotateLeft.addEventListener("click", function () {
        state.rotation = (state.rotation + 270) % 360;
        renderPage(state.pageNumber);
    });
    els.rotateRight.addEventListener("click", function () {
        state.rotation = (state.rotation + 90) % 360;
        renderPage(state.pageNumber);
    });
    els.bookmark.addEventListener("click", function () {
        localStorage.setItem(storagePrefix + "bookmark", String(state.pageNumber));
        els.bookmark.textContent = "Bookmarked";
        window.setTimeout(function () {
            els.bookmark.textContent = "Bookmark";
        }, 1200);
    });
    els.resume.addEventListener("click", function () {
        goToPage(savedPage("bookmark") || savedPage("last-page") || 1);
    });
    els.fullscreen.addEventListener("click", function () {
        if (document.fullscreenElement) {
            document.exitFullscreen();
            return;
        }
        app.requestFullscreen();
    });
    els.searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            runSearch();
        }
    });
    els.searchPrev.addEventListener("click", function () { moveSearch(-1); });
    els.searchNext.addEventListener("click", function () { moveSearch(1); });
    els.themeSelect.addEventListener("change", function () { applyTheme(els.themeSelect.value); });

    document.addEventListener("keydown", function (event) {
        var target = event.target;
        var editing = target && ["INPUT", "SELECT", "TEXTAREA"].indexOf(target.tagName) !== -1;
        if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "f") {
            event.preventDefault();
            els.searchInput.focus();
            els.searchInput.select();
            return;
        }
        if (editing) {
            return;
        }

        if (event.key === "ArrowLeft") {
            goToPage(state.pageNumber - 1);
        } else if (event.key === "ArrowRight") {
            goToPage(state.pageNumber + 1);
        } else if (event.key === "Home") {
            goToPage(1);
        } else if (event.key === "End") {
            goToPage(state.totalPages);
        } else if (event.key === "+" || event.key === "=") {
            setScale(state.scale + 0.25);
        } else if (event.key === "-") {
            setScale(state.scale - 0.25);
        } else if (String(event.key).toLowerCase() === "f") {
            els.fullscreen.click();
        } else if (event.key === "/") {
            event.preventDefault();
            els.searchInput.focus();
        }
    });

    window.addEventListener("resize", function () {
        if (state.fitMode) {
            renderPage(state.pageNumber);
        }
    });

    setControlsDisabled(true);
    setInterval(updateTimer, 1000);
    loadPdf();
})();
