(function () {
    var CONTRAST_STORAGE_KEY = "siteContrastTheme";
    var CONTRAST_OPTIONS = {
        default: true,
        high: true,
        dark: true,
        sepia: true,
        soft: true
    };

    function validContrastTheme(theme) {
        return CONTRAST_OPTIONS[theme] ? theme : "default";
    }

    function currentContrastTheme() {
        try {
            return validContrastTheme(localStorage.getItem(CONTRAST_STORAGE_KEY) || "default");
        } catch (error) {
            return "default";
        }
    }

    function setContrastTheme(theme) {
        var nextTheme = validContrastTheme(theme);
        document.documentElement.dataset.contrastTheme = nextTheme;

        try {
            localStorage.setItem(CONTRAST_STORAGE_KEY, nextTheme);
        } catch (error) {
            // Contrast still applies for this page even when storage is unavailable.
        }

        document.querySelectorAll("[data-contrast-select]").forEach(function (select) {
            select.value = nextTheme;
        });
    }

    function createProgressElement(form, submitter, isUpload) {
        var progress = form.querySelector(".form-progress");
        if (!progress) {
            progress = document.createElement("div");
            progress.className = "form-progress";
            progress.setAttribute("role", "status");
            progress.setAttribute("aria-live", "polite");
            progress.innerHTML = [
                '<span class="form-progress-spinner" aria-hidden="true"></span>',
                '<span data-progress-label></span>',
                '<progress data-progress-bar max="100" value="0" hidden></progress>'
            ].join("");

            if (submitter && submitter.parentNode) {
                submitter.parentNode.insertBefore(progress, submitter.nextSibling);
            } else {
                form.appendChild(progress);
            }
        }

        var bar = progress.querySelector("[data-progress-bar]");
        if (bar) {
            bar.hidden = !isUpload;
            bar.value = 0;
        }
        return progress;
    }

    function setProgress(progress, message, percent) {
        var label = progress.querySelector("[data-progress-label]");
        var bar = progress.querySelector("[data-progress-bar]");
        if (label) {
            label.textContent = message;
        }
        if (bar && typeof percent === "number") {
            bar.value = Math.max(0, Math.min(100, percent));
        }
    }

    function responseErrorMessage(request) {
        try {
            var payload = JSON.parse(request.responseText);
            if (payload.error) {
                return payload.error;
            }
        } catch (error) {
            // The server may return a regular Django error page.
        }

        if (request.status) {
            return "Upload failed with server status " + request.status + ".";
        }
        return "Upload failed. Try again.";
    }

    function setFormBusy(form, submitter, busy) {
        form.querySelectorAll("input, select, textarea, button").forEach(function (control) {
            if (control.type !== "hidden") {
                control.disabled = busy;
            }
        });

        if (submitter) {
            submitter.hidden = busy;
        }
    }

    function restoreForm(form, submitter) {
        form.dataset.submitting = "false";
        setFormBusy(form, submitter, false);
    }

    function uploadWithProgress(form, submitter, progress) {
        var request = new XMLHttpRequest();
        var formData = new FormData(form);
        if (submitter && submitter.name) {
            formData.append(submitter.name, submitter.value);
        }

        setFormBusy(form, submitter, true);

        request.open((form.method || "POST").toUpperCase(), form.action || window.location.href);
        request.setRequestHeader("X-Requested-With", "XMLHttpRequest");

        request.upload.addEventListener("progress", function (event) {
            if (!event.lengthComputable) {
                setProgress(progress, "Uploading...", null);
                return;
            }

            var percent = Math.round((event.loaded / event.total) * 100);
            setProgress(progress, "Uploading... " + percent + "%", percent);
        });

        request.addEventListener("load", function () {
            if (request.status >= 200 && request.status < 400) {
                setProgress(progress, "Processing...", 100);

                try {
                    var payload = JSON.parse(request.responseText);
                    if (payload.redirect_url) {
                        window.location.assign(payload.redirect_url);
                        return;
                    }
                } catch (error) {
                    // Fall back to the final response URL below.
                }

                window.location.assign(request.responseURL || window.location.href);
                return;
            }

            setProgress(progress, responseErrorMessage(request), 0);
            restoreForm(form, submitter);
        });

        request.addEventListener("error", function () {
            setProgress(progress, "Upload failed. Check your connection.", 0);
            restoreForm(form, submitter);
        });

        request.addEventListener("abort", function () {
            setProgress(progress, "Upload canceled.", 0);
            restoreForm(form, submitter);
        });

        request.send(formData);
    }

    document.addEventListener("change", function (event) {
        if (event.target && event.target.matches("[data-contrast-select]")) {
            setContrastTheme(event.target.value);
        }
    });

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        if (form.dataset.submitting === "true") {
            event.preventDefault();
            return;
        }

        var submitter = event.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
        var hasFileInput = Boolean(form.querySelector('input[type="file"]'));
        var isUpload = hasFileInput && window.FormData && window.XMLHttpRequest;
        var progress = createProgressElement(form, submitter, isUpload);

        form.dataset.submitting = "true";
        setProgress(progress, isUpload ? "Uploading... 0%" : "Submitting...", 0);

        if (isUpload) {
            event.preventDefault();
            uploadWithProgress(form, submitter, progress);
            return;
        }

        if (submitter) {
            submitter.hidden = true;
        }
    });

    setContrastTheme(currentContrastTheme());
})();
