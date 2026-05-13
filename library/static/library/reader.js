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
        isRendering: false,
        pendingPage: null,
        contrastOn: false
    };

    var els = {
        canvas: document.getElementById("pdf-canvas"),
        canvasShell: document.getElementById("canvas-shell"),
        loading: document.getElementById("reader-loading"),
        pageStatus: document.getElementById("page-status"),
        pageNumber: document.getElementById("page-number"),
        pageCount: document.getElementById("page-count"),
        contrast: document.getElementById("contrast-toggle"),
        firstPage: document.getElementById("first-page"),
        lastPage: document.getElementById("last-page"),
        fullscreen: document.getElementById("fullscreen-btn"),
        exitFullscreen: document.getElementById("exit-fullscreen-btn"),
        fitWidth: document.getElementById("fit-width"),
        searchPage: document.getElementById("search-page")
    };
    var canvasContext = els.canvas.getContext("2d");

    function setLoading(message) {
        els.loading.textContent = message;
        els.loading.hidden = !message;
    }

    function clampPage(pageNumber) {
        return Math.max(1, Math.min(state.totalPages || 1, Number(pageNumber) || 1));
    }

    function updateStatus() {
        els.pageStatus.textContent = "Page " + state.pageNumber + " of " + state.totalPages;
        els.pageNumber.value = state.pageNumber;
        els.pageNumber.max = state.totalPages || 1;
        els.pageCount.textContent = "/ " + state.totalPages;
    }

    function setControlsDisabled(disabled) {
        [
            els.contrast,
            els.firstPage,
            els.lastPage,
            els.fullscreen,
            els.exitFullscreen,
            els.fitWidth,
            els.searchPage
        ].forEach(function (button) {
            button.disabled = disabled;
        });
        els.pageNumber.disabled = disabled;
    }

    function fitWidthScale(page) {
        var viewport = page.getViewport({ scale: 1 });
        var shellWidth = Math.max(240, els.canvasShell.clientWidth - 36);
        return shellWidth / viewport.width;
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
            var scale = state.fitWidth ? fitWidthScale(page) : 1;
            var viewport = page.getViewport({ scale: scale });
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
            updateStatus();

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

    function toggleContrast() {
        state.contrastOn = !state.contrastOn;
        app.dataset.contrast = state.contrastOn ? "1" : "0";
        els.contrast.classList.toggle("is-active", state.contrastOn);
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

        pdfjsLib.getDocument({ url: app.dataset.pdfUrl }).promise.then(function (pdf) {
            state.pdf = pdf;
            state.totalPages = pdf.numPages;
            updateStatus();
            renderPage(1);
        }).catch(function () {
            setLoading("Could not load this PDF.");
        });
    }

    els.contrast.addEventListener("click", toggleContrast);
    els.firstPage.addEventListener("click", function () { goToPage(1); });
    els.lastPage.addEventListener("click", function () { goToPage(state.totalPages); });
    els.fullscreen.addEventListener("click", enterFullscreen);
    els.exitFullscreen.addEventListener("click", exitFullscreen);
    els.fitWidth.addEventListener("click", function () {
        state.fitWidth = true;
        renderPage(state.pageNumber);
    });
    els.searchPage.addEventListener("click", function () {
        goToPage(els.pageNumber.value);
    });
    els.pageNumber.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            goToPage(els.pageNumber.value);
        }
    });

    window.addEventListener("resize", function () {
        if (state.fitWidth) {
            renderPage(state.pageNumber);
        }
    });

    setControlsDisabled(true);
    app.dataset.contrast = "0";
    loadPdf();
})();
