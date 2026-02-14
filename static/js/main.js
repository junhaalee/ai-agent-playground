document.addEventListener("DOMContentLoaded", () => {
    const btnFetch = document.getElementById("btn-fetch");
    const btnGenerate = document.getElementById("btn-generate");
    const issuesContainer = document.getElementById("issues-container");
    const spinner = document.getElementById("loading-spinner");
    const progressSection = document.getElementById("progress-section");
    const progressBar = document.getElementById("progress-bar");
    const progressText = document.getElementById("progress-text");
    const completionSection = document.getElementById("completion-section");
    const btnUpload = document.getElementById("btn-upload");
    const uploadResult = document.getElementById("upload-result");

    let currentJobId = null;
    let pollTimer = null;

    // --- Fetch Issues ---
    btnFetch.addEventListener("click", async () => {
        btnFetch.disabled = true;
        issuesContainer.innerHTML = "";
        spinner.classList.remove("hidden");
        progressSection.classList.add("hidden");
        completionSection.classList.add("hidden");

        try {
            const resp = await fetch("/api/fetch-issues", { method: "POST" });
            const data = await resp.json();

            spinner.classList.add("hidden");

            if (!resp.ok) {
                issuesContainer.innerHTML =
                    `<div class="error-msg">${data.error || "오류가 발생했습니다."}</div>`;
                return;
            }

            renderKeywordLog(data.keyword_log);
            renderIssues(data.issues, data.article_count);
        } catch (err) {
            spinner.classList.add("hidden");
            issuesContainer.innerHTML =
                `<div class="error-msg">서버에 연결할 수 없습니다.</div>`;
        } finally {
            btnFetch.disabled = false;
        }
    });

    // --- Generate Shorts ---
    btnGenerate.addEventListener("click", async () => {
        const checked = document.querySelectorAll('#issues-container input[type="checkbox"]:checked');
        if (checked.length === 0) {
            alert("이슈를 하나 이상 선택해주세요.");
            return;
        }

        const selectedIndices = Array.from(checked).map(cb => parseInt(cb.value));
        const options = {
            duration: document.getElementById("duration").value,
            subtitle_pos: document.getElementById("subtitle-pos").value,
            speed: document.getElementById("speed").value,
        };

        btnGenerate.disabled = true;
        btnFetch.disabled = true;
        progressSection.classList.remove("hidden");
        completionSection.classList.add("hidden");
        progressBar.style.width = "0%";
        progressText.textContent = "준비 중...";

        try {
            const resp = await fetch("/api/generate-shorts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ selected_indices: selectedIndices, options }),
            });
            const data = await resp.json();

            if (!resp.ok) {
                const errMsg = data.error || "오류가 발생했습니다.";
                progressText.textContent = errMsg;
                progressSection.classList.add("hidden");
                btnGenerate.disabled = false;
                btnFetch.disabled = false;
                alert("영상 생성 요청 실패:\n" + errMsg);
                return;
            }

            currentJobId = data.job_id;
            startPolling();
        } catch (err) {
            progressSection.classList.add("hidden");
            btnGenerate.disabled = false;
            btnFetch.disabled = false;
            alert("서버에 연결할 수 없습니다.");
        }
    });

    // --- Poll Progress ---
    function startPolling() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(pollStatus, 2000);
    }

    async function pollStatus() {
        if (!currentJobId) return;

        try {
            const resp = await fetch(`/api/generation-status/${currentJobId}`);
            const data = await resp.json();

            if (data.error && !data.progress) {
                clearInterval(pollTimer);
                progressText.textContent = data.error;
                btnGenerate.disabled = false;
                btnFetch.disabled = false;
                return;
            }

            const pct = data.progress || 0;
            progressBar.style.width = pct + "%";
            progressText.textContent = data.message || `${pct}%`;

            if (data.status === "completed") {
                clearInterval(pollTimer);
                progressBar.style.width = "100%";
                progressBar.classList.remove("progress-bar-error");
                progressText.textContent = "완료!";
                showCompletion();
            } else if (data.status === "error") {
                clearInterval(pollTimer);
                const errMsg = data.error || "알 수 없는 오류";
                progressBar.classList.add("progress-bar-error");
                progressText.textContent = "오류: " + errMsg;
                btnGenerate.disabled = false;
                btnFetch.disabled = false;
                alert("영상 생성 중 오류가 발생했습니다:\n" + errMsg);
            }
        } catch (err) {
            // Network error, keep polling
        }
    }

    function showCompletion() {
        completionSection.classList.remove("hidden");
        uploadResult.classList.add("hidden");
        btnGenerate.disabled = false;
        btnFetch.disabled = false;
    }

    // --- YouTube Upload ---
    btnUpload.addEventListener("click", async () => {
        const title = document.getElementById("video-title").value.trim();
        const description = document.getElementById("video-desc").value.trim();

        if (!title) {
            alert("영상 제목을 입력해주세요.");
            return;
        }

        btnUpload.disabled = true;
        btnUpload.textContent = "업로드 중...";
        uploadResult.classList.add("hidden");

        try {
            const resp = await fetch("/api/upload-youtube", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    job_id: currentJobId,
                    title,
                    description,
                }),
            });
            const data = await resp.json();

            uploadResult.classList.remove("hidden");

            if (!resp.ok) {
                uploadResult.className = "upload-result error-msg";
                uploadResult.textContent = data.error || "업로드 실패";
            } else {
                uploadResult.className = "upload-result success-msg";
                uploadResult.innerHTML =
                    `업로드 완료! <a href="${escapeHtml(data.url)}" target="_blank">${escapeHtml(data.url)}</a>`;
            }
        } catch (err) {
            uploadResult.classList.remove("hidden");
            uploadResult.className = "upload-result error-msg";
            uploadResult.textContent = "서버에 연결할 수 없습니다.";
        } finally {
            btnUpload.disabled = false;
            btnUpload.textContent = "유튜브 업로드";
        }
    });

    // --- Render Keyword Log ---
    function renderKeywordLog(log) {
        if (!log) return;

        let html = `<div class="keyword-log">`;

        // 트렌딩 키워드 — 항상 표시
        if (log.trending_keywords && log.trending_keywords.length > 0) {
            html += `<div class="keyword-log-item">
                <span class="keyword-log-label">트렌딩 키워드</span>
                <span class="keyword-log-value">${log.trending_keywords.map(k => escapeHtml(k)).join(", ")}</span>
            </div>`;
        } else {
            html += `<div class="keyword-log-item fallback">
                <span class="keyword-log-label">트렌딩 키워드</span>
                <span class="keyword-log-value">수집 실패</span>
            </div>`;
        }

        // 선별된 정치 키워드 + 보충 핫 키워드
        const politicalTags = (log.political_keywords || []).map(k =>
            `<span class="keyword-tag${log.is_fallback ? " fallback-tag" : ""}">${escapeHtml(k)}</span>`
        ).join(" ");
        const hotTags = (log.hot_keywords || []).map(k =>
            `<span class="keyword-tag hot-tag">${escapeHtml(k)}</span>`
        ).join(" ");
        html += `<div class="keyword-log-item">
            <span class="keyword-log-label">검색 키워드</span>
            <span class="keyword-log-value political">${politicalTags} ${hotTags}</span>
            ${log.is_fallback ? '<span class="keyword-fallback-badge">fallback</span>' : ""}
        </div>`;

        html += `</div>`;
        issuesContainer.innerHTML = html;
    }

    // --- Render Issues ---
    function renderIssues(issues, articleCount) {
        if (!issues || issues.length === 0) {
            issuesContainer.innerHTML =
                `<p class="placeholder-text">분석된 이슈가 없습니다.</p>`;
            return;
        }

        let html = "";
        issues.forEach((issue, idx) => {
            html += `
                <div class="issue-item">
                    <input type="checkbox" id="issue-${idx}" value="${idx}">
                    <div class="issue-info">
                        <div class="issue-title">${escapeHtml(issue.title)}</div>
                        <div class="issue-summary">${escapeHtml(issue.summary)}</div>
                        <div class="issue-stats">
                            <span class="stat-articles">관련 기사 ${issue.article_count || 0}건</span>
                        </div>
                    </div>
                </div>`;
        });

        if (articleCount) {
            html += `<div class="article-count">총 ${articleCount}개 기사 분석 완료</div>`;
        }

        issuesContainer.insertAdjacentHTML("beforeend", html);
        updateGenerateButton();
    }

    // Enable/disable generate button based on checkbox selection
    function updateGenerateButton() {
        const observer = new MutationObserver(() => {
            const checked = document.querySelectorAll('#issues-container input[type="checkbox"]:checked');
            btnGenerate.disabled = checked.length === 0;
        });
        observer.observe(issuesContainer, { subtree: true, attributes: true });

        issuesContainer.addEventListener("change", () => {
            const checked = document.querySelectorAll('#issues-container input[type="checkbox"]:checked');
            btnGenerate.disabled = checked.length === 0;
        });
    }

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }
});
