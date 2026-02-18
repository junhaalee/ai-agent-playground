document.addEventListener("DOMContentLoaded", () => {
    const btnFetch = document.getElementById("btn-fetch");
    const btnSearch = document.getElementById("btn-search");
    const btnGenerate = document.getElementById("btn-generate");
    const issuesContainer = document.getElementById("issues-container");
    const spinner = document.getElementById("loading-spinner");
    const progressSection = document.getElementById("progress-section");
    const progressBar = document.getElementById("progress-bar");
    const progressText = document.getElementById("progress-text");
    const completionSection = document.getElementById("completion-section");
    const btnUpload = document.getElementById("btn-upload");
    const uploadResult = document.getElementById("upload-result");

    const MAX_SELECTION = 3;
    let currentJobId = null;
    let pollTimer = null;
    let selectedKeywords = new Set();

    // --- Phase 1: Fetch Trending Keywords ---
    btnFetch.addEventListener("click", async () => {
        btnFetch.disabled = true;
        btnSearch.disabled = true;
        btnGenerate.disabled = true;
        issuesContainer.innerHTML = "";
        spinner.classList.remove("hidden");
        spinner.querySelector("p").textContent = "트렌딩 키워드를 수집하고 있습니다...";
        progressSection.classList.add("hidden");
        completionSection.classList.add("hidden");
        selectedKeywords.clear();

        try {
            const resp = await fetch("/api/fetch-trending", { method: "POST" });
            const data = await resp.json();

            spinner.classList.add("hidden");

            if (!resp.ok) {
                issuesContainer.innerHTML =
                    `<div class="error-msg">${data.error || "오류가 발생했습니다."}</div>`;
                return;
            }

            renderTrendingKeywords(data.keywords, data.is_fallback);
        } catch (err) {
            spinner.classList.add("hidden");
            issuesContainer.innerHTML =
                `<div class="error-msg">서버에 연결할 수 없습니다.</div>`;
        } finally {
            btnFetch.disabled = false;
        }
    });

    // --- Phase 2: Search News with Selected Keywords ---
    btnSearch.addEventListener("click", async () => {
        if (selectedKeywords.size === 0) {
            alert("키워드를 하나 이상 선택해주세요.");
            return;
        }

        btnSearch.disabled = true;
        btnFetch.disabled = true;
        spinner.classList.remove("hidden");
        spinner.querySelector("p").textContent = "뉴스를 분석하고 있습니다...";

        // Remove keyword selection UI but keep the section visible
        const keywordSection = issuesContainer.querySelector(".trending-keywords-section");

        try {
            const resp = await fetch("/api/search-news", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ selected_keywords: Array.from(selectedKeywords) }),
            });
            const data = await resp.json();

            spinner.classList.add("hidden");

            if (!resp.ok) {
                issuesContainer.innerHTML =
                    `<div class="error-msg">${data.error || "오류가 발생했습니다."}</div>`;
                return;
            }

            // Show selected keywords summary + issues
            const selectedSummary = `<div class="keyword-log">
                <div class="keyword-log-item">
                    <span class="keyword-log-label">검색 키워드</span>
                    <span class="keyword-log-value">${Array.from(selectedKeywords).map(k =>
                        `<span class="keyword-tag">${escapeHtml(k)}</span>`
                    ).join(" ")}</span>
                </div>
            </div>`;
            issuesContainer.innerHTML = selectedSummary;

            renderIssues(data.issues, data.article_count);
        } catch (err) {
            spinner.classList.add("hidden");
            issuesContainer.innerHTML =
                `<div class="error-msg">서버에 연결할 수 없습니다.</div>`;
        } finally {
            btnFetch.disabled = false;
            btnSearch.disabled = true;
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
        btnSearch.disabled = true;
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
                showCompletion(data.suggested_title);
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

    function showCompletion(suggestedTitle) {
        completionSection.classList.remove("hidden");
        uploadResult.classList.add("hidden");
        btnGenerate.disabled = false;
        btnFetch.disabled = false;

        const titleInput = document.getElementById("video-title");
        if (suggestedTitle && titleInput) {
            titleInput.value = suggestedTitle;
        }
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

    // --- Render Trending Keywords (Phase 1) ---
    function renderTrendingKeywords(keywords, isFallback) {
        if (!keywords || keywords.length === 0) {
            issuesContainer.innerHTML =
                `<p class="placeholder-text">트렌딩 키워드를 가져오지 못했습니다.</p>`;
            return;
        }

        selectedKeywords.clear();
        updateSearchButton();

        let html = `<div class="trending-keywords-section">`;
        html += `<h3>트렌딩 키워드를 선택하세요 (최대 ${MAX_SELECTION}개)</h3>`;
        html += `<div class="trending-keywords-grid">`;

        keywords.forEach((kw) => {
            const typeClass = kw.is_political ? "political" : "non-political";
            const trafficLabel = kw.traffic > 0 ? `<span class="traffic">${kw.traffic.toLocaleString()}+</span>` : "";
            html += `<div class="trending-keyword ${typeClass}" data-keyword="${escapeHtml(kw.keyword)}">${escapeHtml(kw.keyword)} ${trafficLabel}</div>`;
        });

        html += `</div>`;
        html += `<div class="keyword-select-info"><span class="count">0</span>개 선택됨</div>`;

        if (isFallback) {
            html += `<div class="keyword-fallback-notice">트렌딩 수집 실패 — 기본 정치 키워드를 표시합니다.</div>`;
        }

        html += `</div>`;
        issuesContainer.innerHTML = html;

        // Attach click handlers
        issuesContainer.querySelectorAll(".trending-keyword").forEach((tag) => {
            tag.addEventListener("click", () => onKeywordClick(tag));
        });
    }

    function onKeywordClick(tag) {
        const keyword = tag.dataset.keyword;

        if (tag.classList.contains("selected")) {
            // Deselect
            tag.classList.remove("selected");
            selectedKeywords.delete(keyword);
        } else {
            // Select (if under limit)
            if (selectedKeywords.size >= MAX_SELECTION) return;
            tag.classList.add("selected");
            selectedKeywords.add(keyword);
        }

        updateKeywordUI();
        updateSearchButton();
    }

    function updateKeywordUI() {
        const countEl = issuesContainer.querySelector(".keyword-select-info .count");
        if (countEl) countEl.textContent = selectedKeywords.size;

        const allTags = issuesContainer.querySelectorAll(".trending-keyword");
        allTags.forEach((tag) => {
            if (selectedKeywords.size >= MAX_SELECTION && !tag.classList.contains("selected")) {
                tag.classList.add("disabled");
            } else {
                tag.classList.remove("disabled");
            }
        });
    }

    function updateSearchButton() {
        btnSearch.disabled = selectedKeywords.size === 0;
    }

    // --- Render Issues (Phase 2) ---
    function renderIssues(issues, articleCount) {
        if (!issues || issues.length === 0) {
            issuesContainer.innerHTML +=
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

    function updateGenerateButton() {
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
