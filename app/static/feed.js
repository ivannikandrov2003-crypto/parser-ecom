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
    showStatus("Сбор поставлен в очередь…", "loading");

    try {
        const response = await fetch(refresh.dataset.endpoint, { method: "POST" });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || "Не удалось запустить сбор.");
        }

        const deadline = Date.now() + 120_000;
        while (Date.now() < deadline) {
            await new Promise(resolve => setTimeout(resolve, 2_000));
            const statusResponse = await fetch(refresh.dataset.endpoint);
            if (!statusResponse.ok) throw new Error("Не удалось получить состояние обработки.");

            const status = await statusResponse.json();
            if (status.state === "failed") throw new Error("Не удалось прочитать ни один источник.");
            if (status.state !== "done") {
                showStatus("Читаем источники и собираем новости…", "loading");
                continue;
            }

            const result = status.result;
            const excerpts = result.collected_excerpts ?? 0;
            const deferred = result.deferred_sources ?? 0;
            const message = `Собрано: ${result.collected}, из них по анонсам: ${excerpts}. Отложено источников: ${deferred}. Ожидают обработки: ${status.pending}. Ожидают повтора: ${status.retrying}. Требуют проверки: ${status.needs_review}. Ошибок сбора: ${result.failed_articles + result.failed_sources}.`;
            if (status.pending > status.retrying) {
                showStatus(message, "loading");
                continue;
            }
            rememberResult(message, status.pending || status.needs_review || deferred || result.failed_articles || result.failed_sources ? "warning" : "success");
            return;
        }
        rememberResult("Обработка продолжается в фоне. Готовые новости появятся в ленте.", "warning");
    } catch (error) {
        const message = error instanceof TypeError ? "Не удалось связаться с сервером." : error.message;
        showStatus(message, "error");
        refresh.disabled = false;
        refresh.removeAttribute("aria-busy");
    }
});

function rememberResult(message, state) {
    try {
        sessionStorage.setItem(resultKey, JSON.stringify({ message, state }));
    } catch {
        // Переход к началу ленты доступен без временного хранилища.
    }
    window.location.assign(refresh.dataset.feed);
}

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
