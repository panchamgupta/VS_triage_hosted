document.addEventListener("DOMContentLoaded", function () {
    var baseUrl = (document.body && document.body.dataset.baseUrl) ? document.body.dataset.baseUrl.replace(/\/$/, "") : "";

    function buildReleaseUrl(releaseId) {
        var rel = releaseId ? "/release/" + encodeURIComponent(releaseId) : "#";
        if (!releaseId) {
            return rel;
        }
        return baseUrl ? (baseUrl + rel) : rel;
    }

    function bindReleasePicker(selectElement) {
        if (!selectElement) {
            return;
        }

        var container = selectElement.closest("section, .hero-shell, .panel, .panel-shell, body");
        var openLink = container ? container.querySelector("[data-release-open]") : null;
        if (!openLink) {
            openLink = document.querySelector("[data-release-open]");
        }

        function syncHref() {
            var releaseId = selectElement.value || "";
            if (!openLink) {
                return;
            }
            openLink.href = buildReleaseUrl(releaseId);
            openLink.setAttribute("aria-disabled", releaseId ? "false" : "true");
        }

        selectElement.addEventListener("change", syncHref);
        syncHref();
    }

    document.querySelectorAll("[data-release-picker]").forEach(bindReleasePicker);

    function apiPath(path) {
        return baseUrl ? (baseUrl + path) : path;
    }

    function fileUrl(path) {
        return baseUrl ? (baseUrl + path) : path;
    }

    function asDate(value) {
        if (!value) {
            return null;
        }
        var dt = new Date(value);
        if (Number.isNaN(dt.getTime())) {
            return null;
        }
        return dt;
    }

    function formatElapsedFrom(startIso) {
        var start = asDate(startIso);
        if (!start) {
            return "00:00";
        }
        var now = new Date();
        var sec = Math.max(0, Math.floor((now.getTime() - start.getTime()) / 1000));
        var hh = Math.floor(sec / 3600);
        var mm = Math.floor((sec % 3600) / 60);
        var ss = sec % 60;
        if (hh > 0) {
            return String(hh).padStart(2, "0") + ":" + String(mm).padStart(2, "0") + ":" + String(ss).padStart(2, "0");
        }
        return String(mm).padStart(2, "0") + ":" + String(ss).padStart(2, "0");
    }

    function asciiBar(percent) {
        var width = 20;
        var p = Math.max(0, Math.min(100, Number(percent) || 0));
        var filled = Math.round((p / 100) * width);
        return "[" + "#".repeat(filled) + "-".repeat(width - filled) + "] " + String(Math.round(p)) + "%";
    }

    function setText(id, text) {
        var node = document.getElementById(id);
        if (node) {
            node.textContent = text;
        }
    }

    function terminalStatus(status) {
        return status === "completed" || status === "failed" || status === "canceled" || status === "orphaned";
    }

    function safeLower(value) {
        return String(value || "").toLowerCase();
    }

    function stageDisplay(stage) {
        var s = String(stage || "").trim();
        if (!s) {
            return "Queued";
        }
        return s;
    }

    var jobForm = document.getElementById("job-create-form");
    var feedbackBox = document.getElementById("upload-form-feedback");
    var jobStatusCard = document.getElementById("job-status-card");
    var cancelBtn = document.getElementById("job-cancel-btn");
    var progressWrap = document.getElementById("job-progress-wrap");
    var progressBar = document.getElementById("job-progress-bar");
    var logViewer = document.getElementById("job-log-viewer");
    var logPre = document.getElementById("job-log-pre");
    var outcomePanel = document.getElementById("job-outcome-panel");
    var outcomeTitle = document.getElementById("job-outcome-title");
    var outcomeSubtitle = document.getElementById("job-outcome-subtitle");
    var outcomeActions = document.getElementById("job-outcome-actions");
    var redirectText = document.getElementById("job-redirect-text");
    var currentJobId = "";
    var currentJob = null;
    var pollTimer = null;
    var elapsedTimer = null;
    var redirectTimer = null;
    var redirectCountdown = 0;

    function stopElapsedClock() {
        if (elapsedTimer) {
            window.clearInterval(elapsedTimer);
            elapsedTimer = null;
        }
    }

    function stopRedirect() {
        if (redirectTimer) {
            window.clearInterval(redirectTimer);
            redirectTimer = null;
        }
        redirectCountdown = 0;
        if (redirectText) {
            redirectText.textContent = "";
            redirectText.classList.add("hidden");
        }
    }

    function stopPolling() {
        if (pollTimer) {
            window.clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    function showFeedback(message, isError) {
        if (!feedbackBox) {
            return;
        }
        feedbackBox.textContent = message || "";
        feedbackBox.classList.remove("hidden", "feedback-error", "feedback-ok");
        feedbackBox.classList.add(isError ? "feedback-error" : "feedback-ok");
        if (!message) {
            feedbackBox.classList.add("hidden");
        }
    }

    function resetOutcomePanel() {
        if (!outcomePanel) {
            return;
        }
        outcomePanel.classList.add("hidden");
        if (outcomeActions) {
            outcomeActions.innerHTML = "";
        }
        if (outcomeTitle) {
            outcomeTitle.textContent = "";
        }
        if (outcomeSubtitle) {
            outcomeSubtitle.textContent = "";
        }
        stopRedirect();
    }

    function setProgress(progress, stage, elapsed) {
        var pct = Math.max(0, Math.min(100, Number(progress) || 0));
        if (progressWrap) {
            progressWrap.setAttribute("aria-hidden", "false");
        }
        if (progressBar) {
            progressBar.style.width = String(pct) + "%";
        }
        setText("job-progress-text", asciiBar(pct));
        setText("job-stage-text", "Current Step: " + stageDisplay(stage));
        setText("job-elapsed-text", "Elapsed: " + elapsed);
    }

    function updateStatusGrid(job, elapsed) {
        var metadata = (job && job.metadata) ? job.metadata : {};
        setText("status-job-id", (job && job.job_id) ? job.job_id : "-");
        setText("status-release-id", (job && job.release_id) ? job.release_id : "-");
        setText("status-project", metadata.project_name || "-");
        setText("status-target", metadata.target_name || "-");
        setText("status-state", safeLower(job && job.status ? job.status : "idle"));
        setText("status-progress", String(Math.max(0, Math.min(100, Number(job && job.progress || 0)))) + "%");
        setText("status-stage", stageDisplay(job && job.stage));
        setText("status-elapsed", elapsed || "00:00");
    }

    function updateMessage(job) {
        var msg = document.getElementById("job-message-text");
        var err = document.getElementById("job-error-text");
        if (msg) {
            msg.textContent = (job && job.message) ? String(job.message) : "No active job.";
        }
        if (err) {
            var errorText = (job && job.error) ? String(job.error) : "";
            err.textContent = errorText;
            if (errorText) {
                err.classList.remove("hidden");
            } else {
                err.classList.add("hidden");
            }
        }
    }

    function updateLog(logLines) {
        if (!logPre) {
            return;
        }
        if (!Array.isArray(logLines) || logLines.length === 0) {
            logPre.textContent = "No logs available.";
            return;
        }
        logPre.textContent = logLines.join("\n");
        logPre.scrollTop = logPre.scrollHeight;
    }

    function makeLinkButton(label, href, newTab, secondary) {
        var link = document.createElement("a");
        link.className = secondary ? "button-link secondary" : "button-link";
        link.textContent = label;
        link.href = href;
        if (newTab) {
            link.target = "_blank";
            link.rel = "noopener noreferrer";
        }
        return link;
    }

    function makeActionButton(label, handler, secondary) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = secondary ? "button-link secondary" : "button-link";
        button.textContent = label;
        button.addEventListener("click", handler);
        return button;
    }

    function copyText(text, onDone) {
        var value = String(text || "");
        if (!value) {
            return;
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(value).then(function () {
                if (typeof onDone === "function") {
                    onDone();
                }
            }).catch(function () {});
        }
    }

    function renderSuccess(job) {
        if (!outcomePanel || !outcomeActions) {
            return;
        }
        outcomePanel.classList.remove("hidden");
        outcomePanel.classList.remove("outcome-failure");
        outcomePanel.classList.add("outcome-success");
        outcomeTitle.textContent = "Report Generated Successfully";
        outcomeSubtitle.textContent = "Release ID: " + (job.release_id || "-");
        outcomeActions.innerHTML = "";

        var reportPath = job.release_url || ("/release/" + encodeURIComponent(job.release_id || "") + "/report");
        var releasePath = "/release/" + encodeURIComponent(job.release_id || "");
        var reportUrl = fileUrl(reportPath);
        var releaseUrl = fileUrl(releasePath);
        var detailsUrl = fileUrl("/job/" + encodeURIComponent(job.job_id || ""));

        outcomeActions.appendChild(makeLinkButton("Open Report", reportUrl, false, false));
        outcomeActions.appendChild(makeLinkButton("Open in New Tab", reportUrl, true, true));
        outcomeActions.appendChild(makeLinkButton("Open Release", releaseUrl, false, true));
        outcomeActions.appendChild(makeLinkButton("View Job Details", detailsUrl, false, true));
        outcomeActions.appendChild(makeActionButton("Copy Release ID", function () {
            copyText(job.release_id, function () {
                showFeedback("Release ID copied.", false);
            });
        }, true));
        outcomeActions.appendChild(makeActionButton("Copy Report Link", function () {
            copyText(reportUrl, function () {
                showFeedback("Report link copied.", false);
            });
        }, true));

        redirectCountdown = 8;
        redirectText.classList.remove("hidden");
        redirectText.textContent = "Auto-opening report in " + String(redirectCountdown) + "s.";
        var cancel = makeActionButton("Cancel Auto Redirect", function () {
            stopRedirect();
            showFeedback("Auto redirect canceled.", false);
        }, true);
        outcomeActions.appendChild(cancel);
        stopRedirect();
        redirectCountdown = 8;
        redirectText.classList.remove("hidden");
        redirectTimer = window.setInterval(function () {
            redirectCountdown -= 1;
            if (redirectCountdown <= 0) {
                stopRedirect();
                window.location.href = reportUrl;
                return;
            }
            redirectText.textContent = "Auto-opening report in " + String(redirectCountdown) + "s.";
        }, 1000);
    }

    function renderFailure(job) {
        if (!outcomePanel || !outcomeActions) {
            return;
        }
        outcomePanel.classList.remove("hidden");
        outcomePanel.classList.remove("outcome-success");
        outcomePanel.classList.add("outcome-failure");
        outcomeTitle.textContent = "Report Generation Failed";
        var failStage = (job && job.failure_stage) ? String(job.failure_stage) : stageDisplay(job && job.stage);
        outcomeSubtitle.textContent = "Failure Stage: " + failStage;
        outcomeActions.innerHTML = "";
        outcomeActions.appendChild(makeActionButton("Retry", function () {
            if (jobForm) {
                jobForm.scrollIntoView({ behavior: "smooth", block: "start" });
            }
            showFeedback("Review inputs and submit again.", true);
        }, false));
        if (job && job.job_id) {
            outcomeActions.appendChild(makeLinkButton("View Job Details", fileUrl("/job/" + encodeURIComponent(job.job_id)), false, true));
        }
        if (redirectText) {
            redirectText.classList.add("hidden");
            redirectText.textContent = "";
        }
    }

    function validateUploadForm() {
        if (!jobForm) {
            return { ok: true, message: "" };
        }
        var maxMb = Number(jobForm.dataset.maxUploadMb || "512");
        if (!Number.isFinite(maxMb) || maxMb < 1) {
            maxMb = 512;
        }
        var maxBytes = maxMb * 1024 * 1024;

        var required = [
            { name: "docking_sdf", ext: ".sdf", label: "Docking Pose SDF" },
            { name: "interaction_csv", ext: ".csv", label: "Interaction CSV" }
        ];
        var optional = [
            { name: "property_csv", ext: ".csv", label: "ADME / Property CSV" },
            { name: "protein_pdb", ext: ".pdb", label: "Protein PDB" }
        ];

        var i;
        for (i = 0; i < required.length; i += 1) {
            var reqInput = jobForm.querySelector("input[name='" + required[i].name + "']");
            var reqFile = reqInput && reqInput.files ? reqInput.files[0] : null;
            if (!reqFile) {
                return { ok: false, message: required[i].label + " is required." };
            }
            if (!safeLower(reqFile.name).endsWith(required[i].ext)) {
                return { ok: false, message: required[i].label + " must be " + required[i].ext + "." };
            }
            if (reqFile.size > maxBytes) {
                return { ok: false, message: required[i].label + " exceeds max size of " + String(maxMb) + " MB." };
            }
        }

        for (i = 0; i < optional.length; i += 1) {
            var optInput = jobForm.querySelector("input[name='" + optional[i].name + "']");
            var optFile = optInput && optInput.files ? optInput.files[0] : null;
            if (!optFile) {
                continue;
            }
            if (!safeLower(optFile.name).endsWith(optional[i].ext)) {
                return { ok: false, message: optional[i].label + " must be " + optional[i].ext + "." };
            }
            if (optFile.size > maxBytes) {
                return { ok: false, message: optional[i].label + " exceeds max size of " + String(maxMb) + " MB." };
            }
        }

        return { ok: true, message: "Input files validated." };
    }

    function renderRunningState(job) {
        var elapsed = formatElapsedFrom(job.started_at || job.created_at);
        setProgress(job.progress || 0, job.stage || "Queued", elapsed);
        updateStatusGrid(job, elapsed);
        updateMessage(job);
        resetOutcomePanel();
        if (cancelBtn) {
            cancelBtn.disabled = terminalStatus(job.status);
        }
    }

    function refreshLog(jobId) {
        if (!jobId) {
            return Promise.resolve();
        }
        return fetch(apiPath("/api/jobs/" + encodeURIComponent(jobId) + "/log?max_lines=300"))
            .then(function (response) {
                if (!response.ok) {
                    return null;
                }
                return response.json();
            })
            .then(function (payload) {
                if (!payload) {
                    return;
                }
                updateLog(payload.log_tail || []);
            })
            .catch(function () {});
    }

    function pollJob(jobId, intervalMs) {
        stopPolling();
        fetch(apiPath("/api/jobs/" + encodeURIComponent(jobId)))
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Unable to fetch job status.");
                }
                return response.json();
            })
            .then(function (payload) {
                var job = payload && payload.job ? payload.job : null;
                if (!job) {
                    if (cancelBtn) {
                        cancelBtn.disabled = true;
                    }
                    return;
                }

                currentJob = job;
                renderRunningState(job);

                refreshLog(jobId);

                if (terminalStatus(job.status)) {
                    stopPolling();
                    stopElapsedClock();
                    if (cancelBtn) {
                        cancelBtn.disabled = true;
                    }

                    if (job.status === "completed") {
                        renderSuccess(job);
                    } else {
                        renderFailure(job);
                        if (job.status === "failed") {
                            showFeedback("Job failed. Review stage and logs, then retry.", true);
                        }
                    }
                    return;
                }

                pollTimer = window.setTimeout(function () {
                    pollJob(jobId, intervalMs);
                }, intervalMs);
            })
            .catch(function (err) {
                updateMessage({
                    message: "Unable to query job status.",
                    error: String(err || "Unknown error")
                });
                if (cancelBtn) {
                    cancelBtn.disabled = true;
                }
            });
    }

    if (jobForm) {
        jobForm.addEventListener("submit", function (event) {
            event.preventDefault();
            stopPolling();
            stopElapsedClock();
            stopRedirect();
            resetOutcomePanel();

            var validation = validateUploadForm();
            if (!validation.ok) {
                showFeedback(validation.message, true);
                return;
            }
            showFeedback("Uploading files and creating job.", false);

            var submitBtn = jobForm.querySelector("button[type='submit']");
            if (submitBtn) {
                submitBtn.disabled = true;
            }
            if (cancelBtn) {
                cancelBtn.disabled = false;
            }

            var fd = new FormData(jobForm);
            renderRunningState({
                job_id: "pending",
                status: "queued",
                stage: "Uploading Files",
                progress: 5,
                message: "Submitting files and creating job.",
                release_id: "pending",
                metadata: {
                    project_name: String(fd.get("project_name") || ""),
                    target_name: String(fd.get("target_name") || "")
                },
                created_at: new Date().toISOString()
            });

            fetch(apiPath("/api/jobs"), {
                method: "POST",
                body: fd,
            })
                .then(function (response) {
                    return response.json().then(function (payload) {
                        return { status: response.status, payload: payload };
                    });
                })
                .then(function (result) {
                    if (result.status >= 400) {
                        var message = (result.payload && result.payload.error) ? result.payload.error : "Job creation failed.";
                        showFeedback(message, true);
                        renderFailure({ status: "failed", stage: "Validating Inputs", failure_stage: "Validating Inputs" });
                        updateMessage({ message: "Failed to create job.", error: message });
                        if (cancelBtn) {
                            cancelBtn.disabled = true;
                        }
                        if (submitBtn) {
                            submitBtn.disabled = false;
                        }
                        return;
                    }

                    var job = result.payload && result.payload.job ? result.payload.job : null;
                    if (!job || !job.job_id) {
                        showFeedback("Server returned an invalid job payload.", true);
                        updateMessage({ message: "Server returned an invalid job payload.", error: "Invalid API response." });
                        if (cancelBtn) {
                            cancelBtn.disabled = true;
                        }
                        if (submitBtn) {
                            submitBtn.disabled = false;
                        }
                        return;
                    }

                    currentJobId = job.job_id;
                    currentJob = job;
                    renderRunningState(job);
                    refreshLog(currentJobId);

                    if (submitBtn) {
                        submitBtn.disabled = false;
                    }

                    var intervalSeconds = parseInt(jobForm.dataset.jobPollSeconds || "2", 10);
                    if (!Number.isFinite(intervalSeconds) || intervalSeconds < 1) {
                        intervalSeconds = 2;
                    }
                    stopElapsedClock();
                    elapsedTimer = window.setInterval(function () {
                        if (!currentJob || terminalStatus(currentJob.status)) {
                            return;
                        }
                        var elapsed = formatElapsedFrom(currentJob.started_at || currentJob.created_at);
                        setText("job-elapsed-text", "Elapsed: " + elapsed);
                        setText("status-elapsed", elapsed);
                    }, 1000);

                    pollJob(currentJobId, intervalSeconds * 1000);
                })
                .catch(function (err) {
                    showFeedback("Job request failed before submission.", true);
                    updateMessage({
                        message: "Job request failed before submission.",
                        error: String(err || "Unknown error")
                    });
                    if (cancelBtn) {
                        cancelBtn.disabled = true;
                    }
                    if (submitBtn) {
                        submitBtn.disabled = false;
                    }
                });
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener("click", function () {
            if (!currentJobId) {
                return;
            }
            fetch(apiPath("/api/jobs/" + encodeURIComponent(currentJobId) + "/cancel"), {
                method: "POST",
            })
                .then(function (response) { return response.json(); })
                .then(function (payload) {
                    var job = payload && payload.job ? payload.job : null;
                    if (job) {
                        currentJob = job;
                        renderRunningState(job);
                    }
                    if (job && terminalStatus(job.status)) {
                        if (cancelBtn) {
                            cancelBtn.disabled = true;
                        }
                        stopPolling();
                        stopElapsedClock();
                    }
                })
                .catch(function () {
                    // Leave existing card content; polling can still continue.
                });
        });
    }

    if (logViewer) {
        logViewer.addEventListener("toggle", function () {
            if (logViewer.open && currentJobId) {
                refreshLog(currentJobId);
            }
        });
    }

    var reportShell = document.getElementById("hosted-report-shell");
    if (!reportShell) {
        return;
    }

    var releaseId = reportShell.getAttribute("data-release-id") || "";
    if (!releaseId) {
        return;
    }

    // TODO: In the next slice, replace the iframe preservation layer with direct
    // template-driven extraction of Central Ideas, filter panels, and deep-dive
    // sections while preserving the current class names and layout semantics.
    reportShell.setAttribute("data-shell-ready", "true");
});