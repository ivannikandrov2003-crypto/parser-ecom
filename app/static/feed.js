const refresh = document.querySelector("#refresh");
const statusBanner = document.querySelector("#refresh-status");
const resultKey = "news-feed-refresh-result";

function showStatus(message, state) {
    statusBanner.textContent = message;
    statusBanner.dataset.state = state;
    statusBanner.hidden = false;
}

try {
    const savedResult = sessionStorage.getItem(resultKey);
    if (savedResult) {
        const { message, state } = JSON.parse(savedResult);
        sessionStorage.removeItem(resultKey);
        showStatus(message, state);
    }
} catch {
    // Обновление остаётся доступным при отключённом хранилище браузера.
}

refresh.addEventListener("click", async () => {
    refresh.disabled = true;
    refresh.setAttribute("aria-busy", "true");
    showStatus("Проверяем источники и обрабатываем новые статьи…", "loading");

    try {
        const response = await fetch(refresh.dataset.endpoint, { method: "POST" });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            const message = typeof result.detail === "string" ? result.detail : "Не удалось обновить ленту.";
            throw new Error(message);
        }

        const failed = result.failed_articles > 0 || result.failed_sources > 0;
        const message = failed
            ? `Добавлено публикаций: ${result.indexed}. Ошибки загрузки источников: ${result.failed_sources}. Ошибки обработки статей: ${result.failed_articles}.`
            : result.indexed ? `Добавлено публикаций: ${result.indexed}.` : "Новых публикаций нет.";
        try {
            sessionStorage.setItem(resultKey, JSON.stringify({ message, state: failed ? "warning" : "success" }));
        } catch {
            // Переход к началу ленты не зависит от хранилища браузера.
        }
        window.location.assign(refresh.dataset.feed);
    } catch (error) {
        const message = error instanceof TypeError ? "Не удалось связаться с сервером." : error.message;
        showStatus(message, "error");
        refresh.disabled = false;
        refresh.removeAttribute("aria-busy");
    }
});

const copyStatus = document.querySelector("#copy-status");
const copyDialog = document.querySelector("#copy-dialog");
const copyText = copyDialog.querySelector("textarea");

for (const button of document.querySelectorAll("[data-copy]")) {
    let resetLabel;
    button.addEventListener("click", async () => {
        const card = button.closest(".news-card");
        const summary = card.querySelector(".news-card__summary").textContent.trim();
        const originalUrl = card.querySelector(".news-card__link").href;
        const message = `${summary}\n\nИсточник: ${originalUrl}`;

        try {
            await navigator.clipboard.writeText(message);
        } catch {
            copyText.value = message;
            copyDialog.showModal();
            copyText.focus();
            copyText.select();
            return;
        }

        button.textContent = "Скопировано";
        copyStatus.textContent = "Выжимка и ссылка на оригинал скопированы.";
        clearTimeout(resetLabel);
        resetLabel = setTimeout(() => {
            button.textContent = "Скопировать";
            copyStatus.textContent = "";
        }, 2200);
    });
}
