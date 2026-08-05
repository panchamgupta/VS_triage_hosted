document.addEventListener("DOMContentLoaded", function () {
    var baseUrl = (document.body && document.body.dataset.baseUrl) ? document.body.dataset.baseUrl.replace(/\/$/, "") : "";
    var latestReleasesSnapshot = "";
    var releasesPollTimer = null;
    var releaseSyncBusy = false;

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

    function normalizeReleaseRows(releases) {
        if (!Array.isArray(releases)) {
            return [];
        }
        return releases.map(function (release) {
            var releaseId = String((release && release.release_id) || "").trim();
            return {
                release_id: releaseId,
                display_name: String((release && release.display_name) || releaseId),
                description: String((release && release.description) || ""),
                program: String((release && release.program) || ""),
                target: String((release && release.target) || "-"),
                created_at: String((release && release.created_at) || ""),
                status: String((release && release.status) || ""),
                default: !!(release && release.default)
            };
        }).filter(function (release) {
            return !!release.release_id;
        });
    }

    function releaseSnapshot(releases) {
        return JSON.stringify(releases.map(function (release) {
            return {
                release_id: release.release_id,
                display_name: release.display_name,
                description: release.description,
                program: release.program,
                target: release.target,
                created_at: release.created_at,
                status: release.status,
                default: release.default
            };
        }));
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function renderHomeReleaseTable(releases) {
        var tbody = document.getElementById("release-table-body");
        if (!tbody) {
            return;
        }
        var hasDeleteColumn = !!document.querySelector(".release-table thead .check-col");
        var colspan = hasDeleteColumn ? 7 : 6;
        if (!releases.length) {
            tbody.innerHTML = "<tr><td colspan=\"" + String(colspan) + "\">No valid hosted releases were discovered.</td></tr>";
            return;
        }

        var rowsHtml = releases.map(function (release) {
            var releaseUrl = buildReleaseUrl(release.release_id);
            var statusLabel = release.status || "invalid";
            var statusClass = "status-chip status-" + statusLabel;
            var actionHtml = statusLabel === "published"
                ? ("<a class=\"button-link\" href=\"" + escapeHtml(releaseUrl) + "\">Open</a>")
                : "<span class=\"release-meta\">Unavailable</span>";
            var descriptionHtml = release.description ? ("<div class=\"release-meta\">" + escapeHtml(release.description) + "</div>") : "";
            var defaultChip = release.default ? "<span class=\"status-chip status-default\">default</span>" : "";
            return ""
                + "<tr data-release-row data-release-id=\"" + escapeHtml(release.release_id) + "\">"
                + (hasDeleteColumn
                    ? ("<td class=\"check-col\"><input type=\"checkbox\" class=\"release-select-checkbox\" data-release-select value=\"" + escapeHtml(release.release_id) + "\" aria-label=\"Select " + escapeHtml(release.display_name) + "\"></td>")
                    : "")
                + "<td><div class=\"release-name\">" + escapeHtml(release.display_name) + "</div><div class=\"release-meta\">" + escapeHtml(release.release_id) + "</div>" + descriptionHtml + "</td>"
                + "<td>" + (release.program ? escapeHtml(release.program) : "-") + "</td>"
                + "<td>" + (release.target ? escapeHtml(release.target) : "-") + "</td>"
                + "<td>" + (release.created_at ? escapeHtml(release.created_at) : "-") + "</td>"
                + "<td><span class=\"" + escapeHtml(statusClass) + "\">" + escapeHtml(statusLabel) + "</span>" + defaultChip + "</td>"
                + "<td>" + actionHtml + "</td>"
                + "</tr>";
        }).join("");
        tbody.innerHTML = rowsHtml;
    }

    function syncPickerOptionsFromReleases(releases) {
        document.querySelectorAll("[data-release-picker]").forEach(function (picker) {
            var previousValue = String(picker.value || "").trim();
            var defaultRelease = releases.find(function (release) {
                return !!release.default;
            });
            var preferredReleaseId = defaultRelease ? defaultRelease.release_id : "";
            var optionsHtml = releases.map(function (release) {
                var label = release.display_name + " (" + release.release_id + ")";
                return "<option value=\"" + escapeHtml(release.release_id) + "\">" + escapeHtml(label) + "</option>";
            }).join("");

            if (!optionsHtml) {
                picker.innerHTML = "<option value=\"\">No releases currently available.</option>";
                picker.value = "";
                picker.dispatchEvent(new Event("change"));
                return;
            }

            picker.innerHTML = optionsHtml;

            var hasPrevious = releases.some(function (release) {
                return release.release_id === previousValue;
            });
            if (hasPrevious) {
                picker.value = previousValue;
            } else if (preferredReleaseId && releases.some(function (release) { return release.release_id === preferredReleaseId; })) {
                picker.value = preferredReleaseId;
            } else if (releases.length > 0) {
                picker.selectedIndex = 0;
            }
            picker.dispatchEvent(new Event("change"));
        });
    }

    function setOperationsReleaseLoadState(message, isError, showRetry) {
        var statusNode = document.getElementById("ops-release-load-state");
        var retryBtn = document.getElementById("ops-release-retry");
        if (statusNode) {
            statusNode.textContent = message || "";
            statusNode.style.color = isError ? "#b42318" : "#475467";
        }
        if (retryBtn) {
            retryBtn.style.display = showRetry ? "inline-flex" : "none";
        }
    }

    function updateReleaseCountsFromDom() {
        var badge = document.getElementById("release-count-badge");
        var rows = document.querySelectorAll("[data-release-row]");
        if (badge) {
            badge.textContent = String(rows.length) + " Reports";
        }
        var totalNode = document.getElementById("release-total");
        if (totalNode) {
            totalNode.textContent = String(rows.length);
        }
    }

    function syncDefaultReleaseAction(releases) {
        var link = document.querySelector("[data-open-default-release]");
        if (!link) {
            return;
        }
        var defaultRelease = releases.find(function (release) {
            return !!release.default;
        });
        if (!defaultRelease) {
            link.setAttribute("aria-disabled", "true");
            link.href = "#";
            return;
        }
        link.setAttribute("aria-disabled", "false");
        link.href = buildReleaseUrl(defaultRelease.release_id);
    }

    function wireReleaseDeleteCheckboxListeners() {
        releaseCheckboxes().forEach(function (cb) {
            cb.addEventListener("change", syncReleaseDeleteButton);
        });
        syncReleaseDeleteButton();
    }

    function applySharedReleaseState(releases) {
        renderHomeReleaseTable(releases);
        syncPickerOptionsFromReleases(releases);
        wireReleaseDeleteCheckboxListeners();
        updateReleaseCountsFromDom();
        syncDefaultReleaseAction(releases);
    }

    function fetchReleaseListAndSync() {
        if (releaseSyncBusy) {
            return Promise.resolve([]);
        }
        releaseSyncBusy = true;
        return fetch(apiPath("/api/releases"))
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Unable to fetch releases.");
                }
                return response.json();
            })
            .then(function (payload) {
                var normalized = normalizeReleaseRows(payload && payload.releases ? payload.releases : []);
                if (!normalized.length) {
                    setOperationsReleaseLoadState("No releases currently available.", false, false);
                } else {
                    setOperationsReleaseLoadState("", false, false);
                }
                var snapshot = releaseSnapshot(normalized);
                if (snapshot === latestReleasesSnapshot) {
                    return normalized;
                }
                latestReleasesSnapshot = snapshot;
                applySharedReleaseState(normalized);
                return normalized;
            })
            .catch(function () {
                setOperationsReleaseLoadState("Unable to load available releases.", true, true);
                return [];
            })
            .finally(function () {
                releaseSyncBusy = false;
            });
    }

    function startReleaseAutoSync() {
        var hasReleaseSurface = !!document.querySelector("[data-release-picker], #release-table-body, #voting-exports-panel");
        if (!hasReleaseSurface) {
            return;
        }
        fetchReleaseListAndSync();
        if (releasesPollTimer) {
            window.clearInterval(releasesPollTimer);
        }
        releasesPollTimer = window.setInterval(fetchReleaseListAndSync, 3000);
    }

    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible") {
            fetchReleaseListAndSync();
        }
    });

    var opsReleaseRetryBtn = document.getElementById("ops-release-retry");
    if (opsReleaseRetryBtn) {
        opsReleaseRetryBtn.addEventListener("click", function () {
            setOperationsReleaseLoadState("", false, false);
            fetchReleaseListAndSync();
        });
    }

    var releaseDeleteBtn = document.getElementById("delete-selected-releases-btn");
    var releaseDeleteFeedback = document.getElementById("release-delete-feedback");
    var releaseDeleteModal = document.getElementById("release-delete-modal");
    var releaseDeleteCancelBtn = document.getElementById("release-delete-cancel-btn");
    var releaseDeleteConfirmBtn = document.getElementById("release-delete-confirm-btn");
    var releaseDeleteModalTitle = document.getElementById("release-delete-modal-title");
    var releaseDeleteSelectedList = document.getElementById("release-delete-selected-list");
    var selectedReleaseIdsForDelete = [];

    function releaseCheckboxes() {
        return Array.prototype.slice.call(document.querySelectorAll("[data-release-select]"));
    }

    function selectedReleaseIds() {
        return releaseCheckboxes()
            .filter(function (cb) { return cb.checked; })
            .map(function (cb) { return String(cb.value || "").trim(); })
            .filter(function (releaseId) { return !!releaseId; });
    }

    function showReleaseDeleteFeedback(message, isError) {
        if (!releaseDeleteFeedback) {
            return;
        }
        releaseDeleteFeedback.textContent = message || "";
        releaseDeleteFeedback.classList.remove("hidden", "feedback-error", "feedback-ok");
        releaseDeleteFeedback.classList.add(isError ? "feedback-error" : "feedback-ok");
        if (!message) {
            releaseDeleteFeedback.classList.add("hidden");
        }
    }

    function syncReleaseDeleteButton() {
        if (!releaseDeleteBtn) {
            return;
        }
        var count = selectedReleaseIds().length;
        releaseDeleteBtn.disabled = count < 1;
    }

    function hideReleaseDeleteModal() {
        if (releaseDeleteModal) {
            releaseDeleteModal.classList.add("hidden");
        }
        selectedReleaseIdsForDelete = [];
    }

    function showReleaseDeleteModal(ids) {
        if (!releaseDeleteModal) {
            return;
        }
        selectedReleaseIdsForDelete = ids.slice();
        if (releaseDeleteModalTitle) {
            releaseDeleteModalTitle.textContent = "Delete " + String(ids.length) + " report" + (ids.length === 1 ? "" : "s") + "?";
        }
        if (releaseDeleteSelectedList) {
            releaseDeleteSelectedList.innerHTML = ids.map(function (releaseId) {
                return "- " + releaseId;
            }).join("<br>");
        }
        releaseDeleteModal.classList.remove("hidden");
    }

    function removeDeletedReleaseRows(ids) {
        var toRemove = new Set(ids);
        document.querySelectorAll("[data-release-row]").forEach(function (row) {
            var releaseId = String(row.getAttribute("data-release-id") || "").trim();
            if (toRemove.has(releaseId)) {
                row.remove();
            }
        });

        document.querySelectorAll("[data-release-picker]").forEach(function (picker) {
            Array.prototype.slice.call(picker.options).forEach(function (option) {
                if (toRemove.has(String(option.value || "").trim())) {
                    option.remove();
                }
            });
            if (!picker.value && picker.options.length > 0) {
                picker.selectedIndex = 0;
            }
            picker.dispatchEvent(new Event("change"));
        });
    }

    if (releaseDeleteBtn) {
        wireReleaseDeleteCheckboxListeners();

        releaseDeleteBtn.addEventListener("click", function () {
            var ids = selectedReleaseIds();
            if (!ids.length) {
                showReleaseDeleteFeedback("Select at least one report to delete.", true);
                return;
            }
            showReleaseDeleteFeedback("", false);
            showReleaseDeleteModal(ids);
        });
    }

    if (releaseDeleteCancelBtn) {
        releaseDeleteCancelBtn.addEventListener("click", hideReleaseDeleteModal);
    }

    if (releaseDeleteConfirmBtn) {
        releaseDeleteConfirmBtn.addEventListener("click", function () {
            var ids = selectedReleaseIdsForDelete.slice();
            if (!ids.length) {
                hideReleaseDeleteModal();
                return;
            }

            releaseDeleteConfirmBtn.disabled = true;
            fetch(apiPath("/api/releases/batch-delete"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ release_ids: ids })
            })
                .then(function (response) {
                    return response.json().then(function (payload) {
                        return { status: response.status, payload: payload };
                    });
                })
                .then(function (result) {
                    if (result.status >= 400) {
                        var err = (result.payload && result.payload.error) ? String(result.payload.error) : "Delete request failed.";
                        showReleaseDeleteFeedback(err, true);
                        return;
                    }
                    var deleted = Array.isArray(result.payload.deleted) ? result.payload.deleted : [];
                    var deletedIds = deleted.map(function (item) {
                        return String((item && item.release_id) || "").trim();
                    }).filter(function (releaseId) { return !!releaseId; });
                    fetchReleaseListAndSync();

                    var failed = Array.isArray(result.payload.failed) ? result.payload.failed : [];
                    if (failed.length) {
                        showReleaseDeleteFeedback(
                            "Deleted " + String(deletedIds.length) + " report(s). " + String(failed.length) + " failed.",
                            true
                        );
                    } else {
                        showReleaseDeleteFeedback("Deleted " + String(deletedIds.length) + " report(s).", false);
                    }
                    hideReleaseDeleteModal();
                })
                .catch(function () {
                    showReleaseDeleteFeedback("Unable to delete selected reports right now.", true);
                })
                .finally(function () {
                    releaseDeleteConfirmBtn.disabled = false;
                });
        });
    }

    startReleaseAutoSync();

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
                    target_name: ""
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

    var voteBootstrap = document.getElementById("hosted-report-vote-bootstrap");
    if (!voteBootstrap) {
        return;
    }

    var voteSurface = voteBootstrap.getAttribute("data-vote-surface") || "iframe";
    var frameId = voteBootstrap.getAttribute("data-frame-id") || "hosted-report-shell";
    var reportShell = voteSurface === "iframe" ? document.getElementById(frameId) : null;

    if (voteSurface === "iframe" && !reportShell) {
        return;
    }

    var releaseId = voteBootstrap.getAttribute("data-release-id") || "";
    if (!releaseId) {
        return;
    }

    var voteReleaseEndpoint = voteBootstrap.getAttribute("data-vote-release-endpoint") || ("/api/votes/release/" + encodeURIComponent(releaseId));
    var voteScaffoldEndpoint = voteBootstrap.getAttribute("data-vote-scaffold-endpoint") || "/api/votes/scaffold";
    var voteMoleculeEndpoint = voteBootstrap.getAttribute("data-vote-molecule-endpoint") || "/api/votes/molecule";
    var votePollSeconds = parseInt(voteBootstrap.getAttribute("data-vote-poll-seconds") || "5", 10);
    if (!Number.isFinite(votePollSeconds) || votePollSeconds < 1) {
        votePollSeconds = 5;
    }

    var voteState = {
        username: "",
        scaffoldWidgets: new Map(),
        moleculeWidgets: new Map(),
        latestScaffoldSummaries: {},
        latestMoleculeSummaries: {},
        pollTimer: null,
        surfaceReady: false,
        initializedDocument: null,
        surfaceDoc: null,
        sortPatched: false,
        reactionPanelPatched: false,
    };

    var reviewerShell = document.querySelector("[data-reviewer-shell]");
    var reviewerEmpty = reviewerShell ? reviewerShell.querySelector("[data-reviewer-empty]") : null;
    var reviewerActive = reviewerShell ? reviewerShell.querySelector("[data-reviewer-active]") : null;
    var reviewerInput = reviewerShell ? reviewerShell.querySelector("[data-reviewer-input]") : null;
    var reviewerName = reviewerShell ? reviewerShell.querySelector("[data-reviewer-name]") : null;
    var reviewerSave = reviewerShell ? reviewerShell.querySelector("[data-reviewer-save]") : null;
    var reviewerEdit = reviewerShell ? reviewerShell.querySelector("[data-reviewer-edit]") : null;

    var SCAFFOLD_VOTE_TYPES = [
        { key: "LIKE", label: "Like", icon: "👍" },
        { key: "PRIORITY", label: "High Priority", icon: "⭐" },
        { key: "REJECT", label: "Reject", icon: "👎" }
    ];

    var MOLECULE_VOTE_TYPES = [
        { key: "LIKE", label: "Like", icon: "👍" },
        { key: "PRIORITY", label: "High Priority", icon: "⭐" },
        { key: "REJECT", label: "Reject", icon: "👎" }
    ];

    function voteTypesForObject(objectType) {
        return objectType === "molecule" ? MOLECULE_VOTE_TYPES : SCAFFOLD_VOTE_TYPES;
    }

    function voteApiPath(path) {
        if (path && /^https?:\/\//i.test(path)) {
            return path;
        }
        return apiPath(path);
    }

    function voteLocalStorageKey() {
        return "hosted_portal_username";
    }

    function readStoredUsername() {
        try {
            return String(localStorage.getItem(voteLocalStorageKey()) || "").trim();
        } catch (_err) {
            return "";
        }
    }

    function storeUsername(username) {
        try {
            localStorage.setItem(voteLocalStorageKey(), String(username || "").trim());
        } catch (_err) {
            // Best effort only.
        }
    }

    function renderReviewerState() {
        var current = voteState.username || readStoredUsername();
        if (current) {
            voteState.username = current;
            if (reviewerName) {
                reviewerName.textContent = current;
            }
            if (reviewerEmpty) {
                reviewerEmpty.classList.add("hidden");
            }
            if (reviewerActive) {
                reviewerActive.classList.remove("hidden");
            }
            return current;
        }

        if (reviewerInput) {
            reviewerInput.value = "";
        }
        if (reviewerEmpty) {
            reviewerEmpty.classList.remove("hidden");
        }
        if (reviewerActive) {
            reviewerActive.classList.add("hidden");
        }
        return "";
    }

    function saveReviewerName() {
        if (!reviewerInput) {
            return "";
        }
        var entered = String(reviewerInput.value || "").trim();
        if (!entered) {
            showFeedback("Reviewer name is required before voting.", true);
            reviewerInput.focus();
            return "";
        }
        voteState.username = entered;
        storeUsername(entered);
        renderReviewerState();
        showFeedback("Reviewer name saved.", false);
        return entered;
    }

    function ensureUsername(interactive) {
        var current = voteState.username || readStoredUsername();
        if (current) {
            voteState.username = current;
            renderReviewerState();
            return current;
        }
        if (!interactive) {
            return "";
        }
        if (reviewerInput) {
            if (reviewerEmpty) {
                reviewerEmpty.classList.remove("hidden");
            }
            reviewerInput.focus();
            showFeedback("Enter your reviewer name to enable voting.", true);
            return "";
        }
        return "";
    }

    function buildVoteWidget(doc, objectType, objectId) {
        var wrap = doc.createElement("div");
        wrap.className = "hp-vote-widget hp-vote-widget-" + objectType;
        wrap.setAttribute("data-vote-object-type", objectType);
        wrap.setAttribute("data-vote-object-id", objectId);

        var row = doc.createElement("div");
        row.className = "hp-vote-reaction-row";
        wrap.appendChild(row);

        var voterGroups = doc.createElement("div");
        voterGroups.className = "hp-vote-inline-summaries";
        wrap.appendChild(voterGroups);

        var buttonMap = {};
        var countMap = {};
        var voterMap = {};
        var voteTypes = voteTypesForObject(objectType);
        voteTypes.forEach(function (voteType) {
            var button = doc.createElement("button");
            button.type = "button";
            button.className = "hp-vote-btn";
            button.setAttribute("data-vote-type", voteType.key);
            var label = doc.createElement("span");
            label.className = "hp-vote-btn-label";
            label.textContent = voteType.icon + " " + voteType.label;
            button.appendChild(label);
            var count = doc.createElement("span");
            count.className = "hp-vote-btn-count";
            count.textContent = "0";
            button.appendChild(count);
            button.addEventListener("click", function () {
                handleVoteClick(objectType, objectId, voteType.key);
            });
            row.appendChild(button);
            buttonMap[voteType.key] = button;
            countMap[voteType.key] = count;

            var voterLine = doc.createElement("div");
            voterLine.className = "hp-vote-inline-summary";
            var voterLabel = doc.createElement("span");
            voterLabel.className = "hp-vote-inline-icon";
            voterLabel.textContent = voteType.icon;
            var voterValue = doc.createElement("span");
            voterValue.className = "hp-vote-inline-value";
            voterValue.textContent = "-";
            voterLine.appendChild(voterLabel);
            voterLine.appendChild(voterValue);
            voterGroups.appendChild(voterLine);
            voterMap[voteType.key] = voterValue;
        });

        return {
            root: wrap,
            buttons: buttonMap,
            counts: countMap,
            voters: voterMap,
            _summaryKey: "",
        };
    }

    function formatVoterList(voters, count) {
        var list = Array.isArray(voters) ? voters : [];
        var total = Number(count || 0);
        if (list.length === 0) {
            return { text: "-", full: "" };
        }
        var preview = list.slice(0, 3);
        var extra = list.length - preview.length;
        var text = preview.join(", ");
        if (extra > 0) {
            text += " and " + String(extra) + " more";
        }
        if (total > 0) {
            text += " (" + String(total) + ")";
        }
        return {
            text: text,
            full: list.join(", "),
        };
    }

    function applyVoteSummary(widget, summary) {
        if (!widget || !widget.root.isConnected) {
            return;
        }
        var counts = summary && summary.counts ? summary.counts : { LIKE: 0, PRIORITY: 0, REJECT: 0 };
        var votersByType = summary && summary.voters_by_type ? summary.voters_by_type : { LIKE: [], PRIORITY: [], REJECT: [] };

        // Skip DOM update if nothing changed since last render.
        var newKey = (counts.LIKE || 0) + "|" + (counts.PRIORITY || 0) + "|" + (counts.REJECT || 0) + "|" + (summary && summary.user_vote || "");
        if (widget._summaryKey === newKey) {
            return;
        }
        widget._summaryKey = newKey;

        // Cache latest summary for sort operations.
        var objectType = widget.root.getAttribute("data-vote-object-type") || "scaffold";
        var objectId = widget.root.getAttribute("data-vote-object-id") || "";
        if (objectId && summary) {
            if (objectType === "scaffold") {
                voteState.latestScaffoldSummaries[objectId] = summary;
            } else {
                voteState.latestMoleculeSummaries[objectId] = summary;
            }
        }

        // Part 2: Dim scaffold card when any team member has rejected it.
        if (objectType === "scaffold" && widget.root.parentElement) {
            var rejectCount = Number(counts.REJECT || 0);
            widget.root.parentElement.classList.toggle("hp-scaffold-rejected", rejectCount > 0);
        }

        var selectedVote = summary && summary.user_vote ? String(summary.user_vote) : "";
        voteTypesForObject(objectType).forEach(function (voteType) {
            var button = widget.buttons[voteType.key];
            var count = widget.counts[voteType.key];
            var voterValue = widget.voters[voteType.key];
            if (!button) {
                return;
            }
            if (count) {
                count.textContent = String(Number(counts[voteType.key] || 0));
            }
            if (voterValue) {
                var vlist = votersByType[voteType.key] || [];
                var formatted = formatVoterList(vlist, counts[voteType.key]);
                voterValue.textContent = formatted.text;
                voterValue.title = formatted.full;
            }
            if (selectedVote === voteType.key) {
                button.classList.add("active");
            } else {
                button.classList.remove("active");
            }
        });
    }

    function scaffoldVotePayload(objectId, voteType) {
        return {
            release_id: releaseId,
            scaffold_id: objectId,
            username: voteState.username,
            vote_type: voteType,
        };
    }

    function moleculeVotePayload(objectId, voteType) {
        return {
            release_id: releaseId,
            molecule_id: objectId,
            username: voteState.username,
            vote_type: voteType,
        };
    }

    function handleVoteClick(objectType, objectId, voteType) {
        var username = ensureUsername(true);
        if (!username) {
            return;
        }

        var endpoint = objectType === "molecule" ? voteMoleculeEndpoint : voteScaffoldEndpoint;
        var payload = objectType === "molecule"
            ? moleculeVotePayload(objectId, voteType)
            : scaffoldVotePayload(objectId, voteType);

        fetch(voteApiPath(endpoint), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (!result.ok) {
                    var msg = (result.data && result.data.error) ? result.data.error : "Vote could not be saved.";
                    showFeedback(msg, true);
                    return;
                }
                refreshVoteSummaries();
            })
            .catch(function () {
                showFeedback("Vote request failed.", true);
            });
    }

    function pollUrlWithParams(baseEndpoint, params) {
        var url;
        try {
            url = new URL(voteApiPath(baseEndpoint), window.location.origin);
        } catch (_err) {
            return voteApiPath(baseEndpoint);
        }

        Object.keys(params).forEach(function (key) {
            var value = params[key];
            if (!value) {
                return;
            }
            url.searchParams.set(key, value);
        });
        return url.toString();
    }

    function hideDeactivateControls(surfaceDoc) {
        surfaceDoc.querySelectorAll(".deactivate-control").forEach(function (el) {
            el.style.display = "none";
        });
    }

    function hideStarRankingControls(surfaceDoc) {
        surfaceDoc.querySelectorAll(".star-wrap").forEach(function (el) {
            el.style.display = "none";
        });
        surfaceDoc.querySelectorAll("button").forEach(function (btn) {
            var t = (btn.textContent || "").trim();
            if (t === "Clear All Stars") {
                btn.style.display = "none";
            }
        });
    }

    // Composite vote score: High Priority × 10 + Like votes. Used as sort key.
    function _voteScore(summary) {
        if (!summary || !summary.counts) {
            return 0;
        }
        return Number(summary.counts.PRIORITY || 0) * 10 + Number(summary.counts.LIKE || 0);
    }

    function _count(summary, voteType) {
        if (!summary || !summary.counts) {
            return 0;
        }
        return Number(summary.counts[voteType] || 0);
    }

    function _positiveUniqueUserCount(summary) {
        var voters = (summary && summary.voters_by_type) ? summary.voters_by_type : {};
        var seen = {};
        ["LIKE", "PRIORITY"].forEach(function (k) {
            (voters[k] || []).forEach(function (name) {
                var n = String(name || "").trim();
                if (n) {
                    seen[n] = true;
                }
            });
        });
        return Object.keys(seen).length;
    }

    function _isConsensusPositive(summary, thresholdN) {
        var n = Math.max(1, Number(thresholdN || 3));
        return _positiveUniqueUserCount(summary) >= n && _count(summary, "REJECT") === 0;
    }

    // For "Most Liked Molecules": sum composite molecule scores in a scaffold's deep dive.
    function _getMoleculeScoreSumForScaffold(scaffoldId) {
        var surfaceDoc = voteState.surfaceDoc;
        if (!surfaceDoc || !scaffoldId) {
            return 0;
        }
        var deepDive = surfaceDoc.querySelector(".card[data-scaffold='" + String(scaffoldId).replace(/'/g, "\\'") + "']");
        if (!deepDive) {
            return 0;
        }
        var sum = 0;
        deepDive.querySelectorAll(".moltile[data-mol-id]").forEach(function (tile) {
            var molId = tile.getAttribute("data-mol-id");
            sum += _voteScore(voteState.latestMoleculeSummaries[molId] || null);
        });
        return sum;
    }

    function _getConsensusMoleculeCountForScaffold(scaffoldId, thresholdN) {
        var surfaceDoc = voteState.surfaceDoc;
        if (!surfaceDoc || !scaffoldId) {
            return 0;
        }
        var deepDive = surfaceDoc.querySelector(".card[data-scaffold='" + String(scaffoldId).replace(/'/g, "\\'") + "']");
        if (!deepDive) {
            return 0;
        }
        var total = 0;
        deepDive.querySelectorAll(".moltile[data-mol-id]").forEach(function (tile) {
            var molId = tile.getAttribute("data-mol-id");
            if (_isConsensusPositive(voteState.latestMoleculeSummaries[molId] || null, thresholdN)) {
                total += 1;
            }
        });
        return total;
    }

    function _domSortScaffolds(comparatorFn) {
        var surfaceDoc = voteState.surfaceDoc;
        if (!surfaceDoc) {
            return;
        }
        var grid = surfaceDoc.getElementById("central-idea-grid");
        if (!grid) {
            return;
        }
        var cards = Array.prototype.slice.call(
            grid.querySelectorAll(".idea-card[data-scaffold]"
        ));
        if (cards.length === 0) {
            return;
        }
        cards.sort(comparatorFn);
        cards.forEach(function (card) {
            grid.appendChild(card);
        });
    }

    // Most Liked Scaffolds: Primary = High Priority votes × 10 + Like votes (descending).
    function sortByMostLikedScaffolds() {
        _domSortScaffolds(function (a, b) {
            var aScore = _voteScore(voteState.latestScaffoldSummaries[a.getAttribute("data-scaffold")] || null);
            var bScore = _voteScore(voteState.latestScaffoldSummaries[b.getAttribute("data-scaffold")] || null);
            return bScore - aScore;
        });
    }

    // Most Liked Molecules: Primary = sum of (High Priority × 10 + Like) for all molecules
    // in each scaffold's deep dive (descending). Surfaces scaffolds with the most
    // voted-on molecules.
    function sortByMostLikedMolecules() {
        _domSortScaffolds(function (a, b) {
            var aScore = _getMoleculeScoreSumForScaffold(a.getAttribute("data-scaffold"));
            var bScore = _getMoleculeScoreSumForScaffold(b.getAttribute("data-scaffold"));
            return bScore - aScore;
        });
    }

    function _consensusThresholdFromPanel() {
        var surfaceDoc = voteState.surfaceDoc;
        var input = surfaceDoc ? surfaceDoc.getElementById("hp-consensus-threshold") : null;
        var value = input ? parseInt(input.value || "3", 10) : 3;
        if (!Number.isFinite(value) || value < 1) {
            value = 3;
        }
        if (value > 100) {
            value = 100;
        }
        return value;
    }

    function _sortTiebreakScaffoldId(a, b) {
        var aId = String(a.getAttribute("data-scaffold") || "");
        var bId = String(b.getAttribute("data-scaffold") || "");
        return aId.localeCompare(bId);
    }

    function sortByConsensusScaffolds() {
        var n = _consensusThresholdFromPanel();
        _domSortScaffolds(function (a, b) {
            var aId = a.getAttribute("data-scaffold");
            var bId = b.getAttribute("data-scaffold");
            var aSummary = voteState.latestScaffoldSummaries[aId] || null;
            var bSummary = voteState.latestScaffoldSummaries[bId] || null;

            var aConsensus = _isConsensusPositive(aSummary, n) ? 1 : 0;
            var bConsensus = _isConsensusPositive(bSummary, n) ? 1 : 0;
            if (bConsensus !== aConsensus) {
                return bConsensus - aConsensus;
            }

            var aPositive = _positiveUniqueUserCount(aSummary);
            var bPositive = _positiveUniqueUserCount(bSummary);
            if (bPositive !== aPositive) {
                return bPositive - aPositive;
            }

            var aPriority = _count(aSummary, "PRIORITY");
            var bPriority = _count(bSummary, "PRIORITY");
            if (bPriority !== aPriority) {
                return bPriority - aPriority;
            }

            var aLike = _count(aSummary, "LIKE");
            var bLike = _count(bSummary, "LIKE");
            if (bLike !== aLike) {
                return bLike - aLike;
            }

            var aReject = _count(aSummary, "REJECT");
            var bReject = _count(bSummary, "REJECT");
            if (aReject !== bReject) {
                return aReject - bReject;
            }

            return _sortTiebreakScaffoldId(a, b);
        });
    }

    function sortByConsensusMolecules() {
        var n = _consensusThresholdFromPanel();
        _domSortScaffolds(function (a, b) {
            var aId = a.getAttribute("data-scaffold");
            var bId = b.getAttribute("data-scaffold");
            var aConsensusMol = _getConsensusMoleculeCountForScaffold(aId, n);
            var bConsensusMol = _getConsensusMoleculeCountForScaffold(bId, n);
            if (bConsensusMol !== aConsensusMol) {
                return bConsensusMol - aConsensusMol;
            }

            var aMolScore = _getMoleculeScoreSumForScaffold(aId);
            var bMolScore = _getMoleculeScoreSumForScaffold(bId);
            if (bMolScore !== aMolScore) {
                return bMolScore - aMolScore;
            }

            var aSummary = voteState.latestScaffoldSummaries[aId] || null;
            var bSummary = voteState.latestScaffoldSummaries[bId] || null;
            var aConsensusScf = _isConsensusPositive(aSummary, n) ? 1 : 0;
            var bConsensusScf = _isConsensusPositive(bSummary, n) ? 1 : 0;
            if (bConsensusScf !== aConsensusScf) {
                return bConsensusScf - aConsensusScf;
            }

            var aPriority = _count(aSummary, "PRIORITY");
            var bPriority = _count(bSummary, "PRIORITY");
            if (bPriority !== aPriority) {
                return bPriority - aPriority;
            }

            var aLike = _count(aSummary, "LIKE");
            var bLike = _count(bSummary, "LIKE");
            if (bLike !== aLike) {
                return bLike - aLike;
            }

            return _sortTiebreakScaffoldId(a, b);
        });
    }

    function _surfaceWindow() {
        return voteState.surfaceDoc && voteState.surfaceDoc.defaultView ? voteState.surfaceDoc.defaultView : window;
    }

    function _setReactionStatus(msg, isError) {
        var surfaceDoc = voteState.surfaceDoc;
        var node = surfaceDoc ? surfaceDoc.getElementById("hp-reaction-export-status") : null;
        if (!node) {
            return;
        }
        node.textContent = msg || "";
        node.style.color = isError ? "#b42318" : "#35556e";
    }

    function _reactionScaffoldIds(reactionType) {
        var out = [];
        Object.keys(voteState.latestScaffoldSummaries).forEach(function (scaffoldId) {
            var summary = voteState.latestScaffoldSummaries[scaffoldId] || null;
            if (_count(summary, reactionType) > 0) {
                out.push(scaffoldId);
            }
        });
        return out.sort();
    }

    function _consensusScaffoldIds(thresholdN) {
        var out = [];
        Object.keys(voteState.latestScaffoldSummaries).forEach(function (scaffoldId) {
            var summary = voteState.latestScaffoldSummaries[scaffoldId] || null;
            if (_isConsensusPositive(summary, thresholdN)) {
                out.push(scaffoldId);
            }
        });
        return out.sort();
    }

    function _downloadUrl(url) {
        var a = document.createElement("a");
        a.href = url;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    function _syncAllMembersCheckboxes(scaffoldIds, checked) {
        if (!voteState.surfaceDoc) {
            return;
        }
        var selected = {};
        scaffoldIds.forEach(function (id) { selected[id] = true; });
        voteState.surfaceDoc.querySelectorAll(".all-members-checkbox[data-scaffold]").forEach(function (cb) {
            var sid = String(cb.getAttribute("data-scaffold") || "");
            cb.checked = !!selected[sid] && checked;
        });
    }

    function _clientScaffoldExport(scaffoldIds, includeAllMembers, actionLabel) {
        var win = _surfaceWindow();
        if (!voteState.surfaceDoc || typeof win.syncCheckboxes !== "function" || typeof win.exportSDF !== "function") {
            _setReactionStatus("Report export functions are unavailable in this view.", true);
            return;
        }
        if (!scaffoldIds.length) {
            _setReactionStatus("No matching scaffolds found for " + actionLabel + ".", true);
            return;
        }

        if (typeof win.clearSel === "function") {
            win.clearSel();
        }
        _syncAllMembersCheckboxes([], false);
        scaffoldIds.forEach(function (scaffoldId) {
            win.syncCheckboxes(scaffoldId, true);
        });
        if (includeAllMembers) {
            _syncAllMembersCheckboxes(scaffoldIds, true);
        }
        win.exportSDF();
        _setReactionStatus("Exported " + String(scaffoldIds.length) + " scaffolds for " + actionLabel + ".", false);
    }

    function _filenameFromDisposition(disposition, fallbackName) {
        var text = String(disposition || "");
        var m = text.match(/filename\*=UTF-8''([^;]+)/i);
        if (m && m[1]) {
            try {
                return decodeURIComponent(m[1]);
            } catch (_err) {
                return m[1];
            }
        }
        m = text.match(/filename="?([^";]+)"?/i);
        if (m && m[1]) {
            return m[1];
        }
        return fallbackName || "selected_molecules.sdf";
    }

    function _downloadBlob(filename, blob) {
        var a = document.createElement("a");
        var href = URL.createObjectURL(blob);
        a.href = href;
        a.download = filename || "selected_molecules.sdf";
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.setTimeout(function () {
            URL.revokeObjectURL(href);
        }, 1000);
    }

    function _getMoleculeVoteSnapshot() {
        return fetch(voteApiPath(voteReleaseEndpoint))
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("vote-summary-unavailable");
                }
                return response.json();
            })
            .then(function (payload) {
                return (payload && payload.molecule_votes) ? payload.molecule_votes : {};
            });
    }

    function _getExportPayload(win) {
        if (win && win._EXPORT && typeof win._EXPORT === "object") {
            return win._EXPORT;
        }
        try {
            if (win && typeof win.eval === "function") {
                var payload = win.eval("(typeof _EXPORT !== 'undefined') ? _EXPORT : null");
                if (payload && typeof payload === "object") {
                    return payload;
                }
            }
        } catch (_err) {
            // Best effort only.
        }
        return null;
    }

    function _buildMoleculeMetaIndex() {
        var win = _surfaceWindow();
        var exportPayload = _getExportPayload(win);
        if (!exportPayload || typeof exportPayload !== "object") {
            return {};
        }
        var out = {};
        Object.keys(exportPayload).forEach(function (scaffoldId) {
            var entry = exportPayload[scaffoldId] || {};
            var members = Array.isArray(entry.all_members) ? entry.all_members : [];
            members.forEach(function (member) {
                var molId = String((member && member.mol_id) || "").trim();
                var idx = (member && member.mol_index != null) ? parseInt(member.mol_index, 10) : NaN;
                if (!molId || !Number.isFinite(idx) || out[molId]) {
                    return;
                }
                out[molId] = {
                    idx: idx,
                    label: String((member && member.mol_id) || ("Mol " + String(idx))),
                    scaffold: String(scaffoldId || ""),
                };
            });
        });
        return out;
    }

    function _applyMemberSelectionAndExport(selectedMetas, actionLabel) {
        var win = _surfaceWindow();
        if (typeof win.exportMemberSDF !== "function") {
            _setReactionStatus("Report export functions are unavailable in this view.", true);
            return false;
        }

        if (typeof win.clearMemberSel === "function") {
            win.clearMemberSel();
        }

        try {
            win.__hpMemberSelectionPayload = selectedMetas;
            var applied = false;
            if (typeof win.eval === "function") {
                applied = !!win.eval(
                    "(function(){" +
                    "var sel=window.__hpMemberSelectionPayload||[];" +
                    "if(typeof _MEMBER_SEL==='undefined'){return false;}" +
                    "Object.keys(_MEMBER_SEL).forEach(function(k){delete _MEMBER_SEL[k];});" +
                    "sel.forEach(function(m){" +
                    "if(!m||m.idx==null){return;}" +
                    "_MEMBER_SEL[String(m.idx)]={idx:m.idx,label:String(m.label||('Mol '+String(m.idx))),scaffold:String(m.scaffold||'')};" +
                    "});" +
                    "if(typeof _persistMemberSel==='function'){_persistMemberSel();}" +
                    "if(typeof _updateToolbar==='function'){_updateToolbar();}" +
                    "return true;" +
                    "})()"
                );
            }
            delete win.__hpMemberSelectionPayload;

            if (!applied) {
                _setReactionStatus("No molecules currently match this selection.", true);
                return false;
            }
        } catch (_err) {
            _setReactionStatus("No molecules currently match this selection.", true);
            return false;
        }

        var selectedIdx = {};
        selectedMetas.forEach(function (meta) {
            selectedIdx[String(meta.idx)] = true;
        });
        if (voteState.surfaceDoc) {
            voteState.surfaceDoc.querySelectorAll(".member-export-toggle").forEach(function (cb) {
                var idx = String(cb.getAttribute("data-mol-index") || "");
                cb.checked = !!selectedIdx[idx];
                var tile = cb.closest ? cb.closest(".moltile") : null;
                if (tile) {
                    tile.classList.toggle("member-sel-active", !!selectedIdx[idx]);
                }
            });
        }

        win.exportMemberSDF();
        _setReactionStatus("Selected " + String(selectedMetas.length) + " " + actionLabel.toLowerCase() + ".", false);
        return true;
    }

    function _qualifyingMoleculeIds(voteMap, mode, thresholdN) {
        var ids = [];
        Object.keys(voteMap || {}).forEach(function (moleculeId) {
            var summary = voteMap[moleculeId] || null;
            if (mode === "LIKE" && _count(summary, "LIKE") > 0) {
                ids.push(moleculeId);
                return;
            }
            if (mode === "PRIORITY" && _count(summary, "PRIORITY") > 0) {
                ids.push(moleculeId);
                return;
            }
            if (mode === "CONSENSUS" && _isConsensusPositive(summary, thresholdN)) {
                ids.push(moleculeId);
            }
        });
        return ids.sort();
    }

    function _noMoleculeMessage(mode) {
        if (mode === "LIKE") {
            return "No liked molecules found.";
        }
        if (mode === "PRIORITY") {
            return "No High Priority molecules found.";
        }
        return "No Consensus molecules found.";
    }

    function _clientMoleculeExportFromVotes(mode, actionLabel) {
        var thresholdN = _consensusThresholdFromPanel();
        _getMoleculeVoteSnapshot()
            .then(function (voteMap) {
                var qualifyingIds = _qualifyingMoleculeIds(voteMap, mode, thresholdN);
                if (!qualifyingIds.length) {
                    _setReactionStatus(_noMoleculeMessage(mode), false);
                    return;
                }

                var metaIndex = _buildMoleculeMetaIndex();
                var selectedMetas = [];
                qualifyingIds.forEach(function (moleculeId) {
                    var meta = metaIndex[moleculeId];
                    if (meta) {
                        selectedMetas.push(meta);
                    }
                });

                if (!selectedMetas.length) {
                    _setReactionStatus("No molecules currently match this selection.", false);
                    return;
                }

                _applyMemberSelectionAndExport(selectedMetas, actionLabel);
            })
            .catch(function () {
                _setReactionStatus("Unable to resolve molecule selections for export right now.", true);
            });
    }

    function _serverMoleculeExport(path, actionLabel, mode) {
        fetch(apiPath(path))
            .then(function (response) {
                var contentType = String(response.headers.get("content-type") || "").toLowerCase();

                if (response.ok) {
                    return response.blob().then(function (blob) {
                        if (!blob || !blob.size) {
                            _setReactionStatus("No molecules currently match this selection.", false);
                            return;
                        }
                        var filename = _filenameFromDisposition(
                            response.headers.get("content-disposition"),
                            actionLabel.toLowerCase().replace(/\s+/g, "_") + ".sdf"
                        );
                        _downloadBlob(filename, blob);
                        _setReactionStatus("Started export for " + actionLabel + ".", false);
                    });
                }

                if (contentType.indexOf("application/json") >= 0) {
                    return response.json().then(function (payload) {
                        var message = String((payload && payload.error) || "").trim();
                        if (message) {
                            _setReactionStatus(message, false);
                            return;
                        }
                        if (response.status === 404) {
                            _clientMoleculeExportFromVotes(mode, actionLabel);
                            return;
                        }
                        _setReactionStatus("No molecules currently match this selection.", false);
                    });
                }

                if (response.status === 404) {
                    // Missing route or stale deployment: fallback to local selection workflow.
                    _clientMoleculeExportFromVotes(mode, actionLabel);
                    return;
                }

                _setReactionStatus("Unable to export molecules right now.", true);
            })
            .catch(function () {
                _clientMoleculeExportFromVotes(mode, actionLabel);
            });
    }

    function _clearAllExportSelections() {
        var win = _surfaceWindow();
        if (typeof win.clearSel === "function") {
            win.clearSel();
        }
        if (typeof win.clearMemberSel === "function") {
            win.clearMemberSel();
        }

        if (voteState.surfaceDoc) {
            voteState.surfaceDoc.querySelectorAll(".all-members-checkbox").forEach(function (cb) {
                cb.checked = false;
            });
            voteState.surfaceDoc.querySelectorAll(".scaf-checkbox").forEach(function (cb) {
                cb.checked = false;
            });
            voteState.surfaceDoc.querySelectorAll(".member-export-toggle").forEach(function (cb) {
                cb.checked = false;
                var tile = cb.closest ? cb.closest(".moltile") : null;
                if (tile) {
                    tile.classList.remove("member-sel-active");
                }
            });
            voteState.surfaceDoc.querySelectorAll(".sel-active").forEach(function (el) {
                el.classList.remove("sel-active");
            });
        }

        _setReactionStatus("Cleared all export selections.", false);
    }

    function patchReactionExportPanel(surfaceDoc) {
        if (voteState.reactionPanelPatched || !surfaceDoc) {
            return;
        }
        voteState.reactionPanelPatched = true;

        var panelActions = surfaceDoc.querySelector(".panel-actions");
        if (!panelActions || surfaceDoc.getElementById("hp-reaction-export-panel")) {
            return;
        }

        var wrap = surfaceDoc.createElement("div");
        wrap.id = "hp-reaction-export-panel";
        wrap.className = "hp-reaction-export-panel";

        var title = surfaceDoc.createElement("div");
        title.className = "hp-reaction-export-title";
        title.textContent = "Reaction-Based Exports";
        wrap.appendChild(title);

        var thresholdRow = surfaceDoc.createElement("div");
        thresholdRow.className = "hp-reaction-threshold";
        thresholdRow.innerHTML = '<label>Consensus threshold (N): <input id="hp-consensus-threshold" type="number" min="1" max="100" value="3" /></label>';
        wrap.appendChild(thresholdRow);

        function addButtonRow(labels) {
            var row = surfaceDoc.createElement("div");
            row.className = "hp-reaction-row";
            labels.forEach(function (item) {
                var btn = surfaceDoc.createElement("button");
                btn.type = "button";
                btn.className = "hp-reaction-btn";
                btn.textContent = item.label;
                btn.addEventListener("click", item.onClick);
                row.appendChild(btn);
            });
            wrap.appendChild(row);
        }

        addButtonRow([
            {
                label: "Download Liked Scaffolds",
                onClick: function () { _clientScaffoldExport(_reactionScaffoldIds("LIKE"), false, "Liked Scaffolds"); }
            },
            {
                label: "Download Liked Scaffolds (All Members)",
                onClick: function () { _clientScaffoldExport(_reactionScaffoldIds("LIKE"), true, "Liked Scaffolds (All Members)"); }
            },
            {
                label: "Download Liked Molecules",
                onClick: function () {
                    _serverMoleculeExport(
                        "/api/exports/reaction/molecules?release_id=" + encodeURIComponent(releaseId) + "&reaction_type=LIKE",
                        "Liked Molecules",
                        "LIKE"
                    );
                }
            }
        ]);

        addButtonRow([
            {
                label: "Download High Priority Scaffolds",
                onClick: function () { _clientScaffoldExport(_reactionScaffoldIds("PRIORITY"), false, "High Priority Scaffolds"); }
            },
            {
                label: "Download High Priority Scaffolds (All Members)",
                onClick: function () { _clientScaffoldExport(_reactionScaffoldIds("PRIORITY"), true, "High Priority Scaffolds (All Members)"); }
            },
            {
                label: "Download High Priority Molecules",
                onClick: function () {
                    _serverMoleculeExport(
                        "/api/exports/reaction/molecules?release_id=" + encodeURIComponent(releaseId) + "&reaction_type=PRIORITY",
                        "High Priority Molecules",
                        "PRIORITY"
                    );
                }
            }
        ]);

        addButtonRow([
            {
                label: "Download Consensus Scaffolds",
                onClick: function () {
                    var n = _consensusThresholdFromPanel();
                    _clientScaffoldExport(_consensusScaffoldIds(n), false, "Consensus Scaffolds");
                }
            },
            {
                label: "Download Consensus Scaffolds (All Members)",
                onClick: function () {
                    var n = _consensusThresholdFromPanel();
                    _clientScaffoldExport(_consensusScaffoldIds(n), true, "Consensus Scaffolds (All Members)");
                }
            },
            {
                label: "Download Consensus Molecules",
                onClick: function () {
                    var n = _consensusThresholdFromPanel();
                    _serverMoleculeExport(
                        "/api/exports/consensus/molecules?release_id=" + encodeURIComponent(releaseId) + "&consensus_threshold_n=" + encodeURIComponent(String(n)),
                        "Consensus Molecules",
                        "CONSENSUS"
                    );
                }
            }
        ]);

        addButtonRow([
            {
                label: "Clear All Selections",
                onClick: function () {
                    _clearAllExportSelections();
                }
            }
        ]);

        var status = surfaceDoc.createElement("div");
        status.id = "hp-reaction-export-status";
        status.className = "hp-reaction-status";
        wrap.appendChild(status);

        panelActions.parentNode.insertBefore(wrap, panelActions.nextSibling);
    }

    function patchSortButtons(surfaceDoc) {
        if (voteState.sortPatched) {
            return;
        }
        voteState.sortPatched = true;

        // Hide legacy star-sort controls wherever they appear.
        surfaceDoc.querySelectorAll("button").forEach(function (btn) {
            var t = (btn.textContent || "").trim();
            if (t === "Sort Starred to Top" || t === "Clear All Stars") {
                btn.style.display = "none";
            }
        });

        // Insert vote-based sort buttons into .panel-actions (works even when
        // the legacy "Sort Starred to Top" button has been removed from new reports).
        var panelActions = surfaceDoc.querySelector(".panel-actions");
        if (!panelActions) {
            return;
        }

        var btnClass = "";
        var existingBtn = panelActions.querySelector("button");
        if (existingBtn) {
            btnClass = existingBtn.className || "";
        }

        var molBtn = surfaceDoc.createElement("button");
        molBtn.type = "button";
        molBtn.textContent = "Most Liked Molecules";
        molBtn.className = btnClass;
        molBtn.addEventListener("click", sortByMostLikedMolecules);

        var consensusMolBtn = surfaceDoc.createElement("button");
        consensusMolBtn.type = "button";
        consensusMolBtn.textContent = "Consensus Molecules";
        consensusMolBtn.className = btnClass;
        consensusMolBtn.addEventListener("click", sortByConsensusMolecules);

        var likedBtn = surfaceDoc.createElement("button");
        likedBtn.type = "button";
        likedBtn.textContent = "Most Liked Scaffolds";
        likedBtn.className = btnClass;
        likedBtn.addEventListener("click", sortByMostLikedScaffolds);

        var consensusBtn = surfaceDoc.createElement("button");
        consensusBtn.type = "button";
        consensusBtn.textContent = "Consensus Scaffolds";
        consensusBtn.className = btnClass;
        consensusBtn.addEventListener("click", sortByConsensusScaffolds);

        // Prepend so vote-based sorts appear first.
        panelActions.insertBefore(consensusMolBtn, panelActions.firstChild);
        panelActions.insertBefore(consensusBtn, panelActions.firstChild);
        panelActions.insertBefore(molBtn, panelActions.firstChild);
        panelActions.insertBefore(likedBtn, panelActions.firstChild);
    }

    function refreshVoteSummaries() {
        if (!voteState.surfaceReady) {
            return;
        }
        // Skip polling when the browser tab is hidden - no need to update invisible UI.
        if (typeof document !== "undefined" && document.hidden) {
            return;
        }

        // Re-bind scaffold widgets for grid pagination (cheap: only visible page cards).
        // Molecule re-binding is handled by the deep-dive MutationObserver - not here.
        if (voteState.surfaceDoc) {
            bindScaffoldWidgets(voteState.surfaceDoc);
        }

        var params = {};
        var username = ensureUsername(false);
        if (username) {
            params.username = username;
        }

        var scaffoldIds = Array.from(voteState.scaffoldWidgets.keys());
        // Only request data for molecule widgets currently visible in the live DOM.
        var moleculeIds = Array.from(voteState.moleculeWidgets.keys()).filter(function (id) {
            var w = voteState.moleculeWidgets.get(id);
            return w && w.root.isConnected;
        });
        if (scaffoldIds.length > 0 && scaffoldIds.length <= 250) {
            params.scaffold_ids = scaffoldIds.join(",");
        }
        if (moleculeIds.length > 0 && moleculeIds.length <= 250) {
            params.molecule_ids = moleculeIds.join(",");
        }

        fetch(pollUrlWithParams(voteReleaseEndpoint, params))
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("vote-poll-failed");
                }
                return response.json();
            })
            .then(function (payload) {
                var scaffoldMap = (payload && payload.scaffold_votes) ? payload.scaffold_votes : {};
                var moleculeMap = (payload && payload.molecule_votes) ? payload.molecule_votes : {};

                // applyVoteSummary internally checks isConnected and _summaryKey;
                // disconnected or unchanged widgets are skipped with no DOM work.
                voteState.scaffoldWidgets.forEach(function (widget, scaffoldId) {
                    applyVoteSummary(widget, scaffoldMap[scaffoldId] || null);
                });
                voteState.moleculeWidgets.forEach(function (widget, moleculeId) {
                    applyVoteSummary(widget, moleculeMap[moleculeId] || null);
                });
            })
            .catch(function () {
                // Poll failures are transient; keep next cycle running.
            });
    }

    function scheduleVotePolling() {
        if (voteState.pollTimer) {
            window.clearInterval(voteState.pollTimer);
        }
        voteState.pollTimer = window.setInterval(refreshVoteSummaries, votePollSeconds * 1000);
    }

    function injectVoteStyles(surfaceDoc) {
        var style = surfaceDoc.getElementById("hp-voting-style");
        if (style) {
            return;
        }
        style = surfaceDoc.createElement("style");
        style.id = "hp-voting-style";
        style.textContent = [
            ".hp-vote-widget { border-top: 1px solid #dfe6ef; margin-top: 12px; padding-top: 10px; font-size: 12px; color: #1f3551; }",
            ".hp-vote-reaction-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }",
            ".hp-vote-widget-molecule .hp-vote-reaction-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }",
            ".hp-vote-btn { border: 1px solid #d3dde8; background: linear-gradient(180deg, #ffffff 0%, #f6f9fc 100%); color: #1f3551; border-radius: 12px; font-size: 11px; line-height: 1.25; padding: 7px 6px; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 3px; min-height: 52px; }",
            ".hp-vote-btn:hover { background: #eef5ff; border-color: #adc6df; }",
            ".hp-vote-btn.active { background: linear-gradient(180deg, #e9f7ef 0%, #d7efe2 100%); color: #0b6e4f; border-color: #8fceb0; }",
            ".hp-vote-btn-label { font-weight: 700; text-align: center; }",
            ".hp-vote-btn-count { font-size: 16px; font-weight: 700; color: #183452; }",
            ".hp-vote-btn.active .hp-vote-btn-count { color: #0b6e4f; }",
            ".hp-vote-inline-summaries { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; }",
            ".hp-vote-inline-summary { display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; color: #40586f; }",
            ".hp-vote-inline-icon { font-size: 13px; line-height: 1; }",
            ".hp-vote-inline-value { color: #1f3551; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }",
            ".hp-vote-widget-molecule { margin-top: 8px; padding-top: 8px; }",
            ".hosted-raw-report-shell { padding: 16px 20px 0; }",
            ".hosted-raw-review-shell { margin-top: 0; }",
            ".idea-card.hp-scaffold-rejected { opacity: 0.45; filter: grayscale(25%); transition: opacity 0.3s ease; }",
            ".idea-card.hp-scaffold-rejected:hover { opacity: 0.75; }",
            ".hp-reaction-export-panel { margin: 10px 0 18px; padding: 10px; border: 1px solid #d9e4ef; border-radius: 10px; background: linear-gradient(180deg,#f9fcff 0%,#f4f8fc 100%); }",
            ".hp-reaction-export-title { font-weight: 700; color: #17324d; margin-bottom: 8px; }",
            ".hp-reaction-threshold { margin-bottom: 8px; font-size: 12px; color: #35556e; }",
            ".hp-reaction-threshold input { width: 70px; margin-left: 6px; }",
            ".hp-reaction-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }",
            ".hp-reaction-btn { border: 1px solid #cad8e7; border-radius: 8px; background: #ffffff; color: #1e3d59; font-size: 12px; padding: 6px 8px; cursor: pointer; }",
            ".hp-reaction-btn:hover { background: #ecf4ff; }",
            ".hp-reaction-status { margin-top: 6px; min-height: 16px; font-size: 12px; color: #35556e; }",
            "@media (max-width: 700px) { .hp-vote-reaction-row { grid-template-columns: repeat(3, minmax(0, 1fr)); } .hp-vote-inline-summaries { gap: 6px 10px; } .hp-vote-inline-summary { flex-basis: 100%; } }"
        ].join("\n");
        surfaceDoc.head.appendChild(style);
    }

    function bindScaffoldWidgets(frameDoc) {
        var cards = frameDoc.querySelectorAll(".idea-card[data-scaffold]");
        cards.forEach(function (card) {
            var scaffoldId = String(card.getAttribute("data-scaffold") || "").trim();
            if (!scaffoldId) {
                return;
            }
            var existing = voteState.scaffoldWidgets.get(scaffoldId);
            // Skip only if the widget root is still attached to the live DOM.
            if (existing && existing.root.isConnected) {
                return;
            }
            var widget = buildVoteWidget(frameDoc, "scaffold", scaffoldId);
            card.appendChild(widget.root);
            voteState.scaffoldWidgets.set(scaffoldId, widget);
        });
    }

    function bindMoleculeWidgets(frameDoc) {
        var tiles = frameDoc.querySelectorAll(".moltile[data-mol-id]");
        tiles.forEach(function (tile) {
            var moleculeId = String(tile.getAttribute("data-mol-id") || "").trim();
            if (!moleculeId) {
                return;
            }
            var existing = voteState.moleculeWidgets.get(moleculeId);
            // Skip only if the widget root is still attached to the live DOM.
            if (existing && existing.root.isConnected) {
                return;
            }
            var widget = buildVoteWidget(frameDoc, "molecule", moleculeId);
            tile.appendChild(widget.root);
            voteState.moleculeWidgets.set(moleculeId, widget);
        });
    }

    // Observe the scaffold grid and deep-dive shell for innerHTML replacements
    // so that vote widgets, deactivate hiders, and star hiders are re-applied
    // immediately — not waiting for the next 5-second poll cycle.
    //
    // IMPORTANT: both observers use childList:true, subtree:false (default).
    // Using subtree:true on deep-dive-shell would fire for every widget.appendChild()
    // call inside bindMoleculeWidgets, creating a feedback loop of O(n^2) DOM work.
    function observeGridAndDeepDive(surfaceDoc) {
        var grid = surfaceDoc.getElementById("central-idea-grid");
        if (grid && !grid._hpObserver) {
            var gridPending = false;
            grid._hpObserver = new MutationObserver(function (mutations) {
                var added = false;
                for (var i = 0; i < mutations.length; i++) {
                    if (mutations[i].addedNodes.length > 0) { added = true; break; }
                }
                if (!added || gridPending) { return; }
                gridPending = true;
                // Microtask: coalesces multiple mutation records from one innerHTML replace.
                Promise.resolve().then(function () {
                    gridPending = false;
                    bindScaffoldWidgets(surfaceDoc);
                    hideDeactivateControls(surfaceDoc);
                    hideStarRankingControls(surfaceDoc);
                    voteState.scaffoldWidgets.forEach(function (widget, id) {
                        var s = voteState.latestScaffoldSummaries[id];
                        if (s) { applyVoteSummary(widget, s); }
                    });
                });
            });
            grid._hpObserver.observe(grid, { childList: true }); // subtree:false
        }

        var shell = surfaceDoc.getElementById("deep-dive-shell");
        if (shell && !shell._hpObserver) {
            var shellPending = false;
            shell._hpObserver = new MutationObserver(function (mutations) {
                var added = false;
                for (var i = 0; i < mutations.length; i++) {
                    if (mutations[i].addedNodes.length > 0) { added = true; break; }
                }
                if (!added || shellPending) { return; }
                shellPending = true;
                Promise.resolve().then(function () {
                    shellPending = false;
                    bindMoleculeWidgets(surfaceDoc);
                    hideDeactivateControls(surfaceDoc);
                    hideStarRankingControls(surfaceDoc);
                    voteState.moleculeWidgets.forEach(function (widget, id) {
                        var s = voteState.latestMoleculeSummaries[id];
                        if (s) { applyVoteSummary(widget, s); }
                    });
                });
            });
            // subtree:false: only watch when _renderDeepDivesForVisible replaces shell's
            // direct children. Our own widget.appendChild calls are on grandchildren
            // and will NOT re-trigger this observer.
            shell._hpObserver.observe(shell, { childList: true }); // subtree:false
        }
    }

    function initializeVotingInDocument(surfaceDoc) {
        if (!surfaceDoc || voteState.initializedDocument === surfaceDoc) {
            return;
        }

        voteState.surfaceDoc = surfaceDoc;
        voteState.initializedDocument = surfaceDoc;
        injectVoteStyles(surfaceDoc);
        bindScaffoldWidgets(surfaceDoc);
        bindMoleculeWidgets(surfaceDoc);
        hideDeactivateControls(surfaceDoc);
        hideStarRankingControls(surfaceDoc);
        patchSortButtons(surfaceDoc);
        patchReactionExportPanel(surfaceDoc);
        // MutationObserver re-injects immediately after each grid/deep-dive re-render.
        observeGridAndDeepDive(surfaceDoc);
        voteState.surfaceReady = true;
        refreshVoteSummaries();
        scheduleVotePolling();
    }

    function initializeVotingInFrame() {
        var frameDoc;
        try {
            frameDoc = reportShell.contentDocument || (reportShell.contentWindow && reportShell.contentWindow.document);
        } catch (_err) {
            return;
        }
        initializeVotingInDocument(frameDoc);
    }

    if (reportShell) {
        reportShell.addEventListener("load", initializeVotingInFrame);
    }

    if (reviewerSave) {
        reviewerSave.addEventListener("click", function () {
            saveReviewerName();
        });
    }

    if (reviewerEdit) {
        reviewerEdit.addEventListener("click", function () {
            voteState.username = "";
            storeUsername("");
            renderReviewerState();
            if (reviewerInput) {
                reviewerInput.focus();
            }
        });
    }

    if (reviewerInput) {
        reviewerInput.addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
                saveReviewerName();
            }
        });
    }

    renderReviewerState();

    // TODO: In the next slice, replace the iframe preservation layer with direct
    // template-driven extraction of Central Ideas, filter panels, and deep-dive
    // sections while preserving the current class names and layout semantics.
    if (reportShell) {
        reportShell.setAttribute("data-shell-ready", "true");
    }

    if (voteSurface === "inline") {
        initializeVotingInDocument(document);
    } else if (reportShell.contentDocument && reportShell.contentDocument.readyState === "complete") {
        // Handle already-loaded iframe (bfcache/browser restore).
        initializeVotingInFrame();
    }
});