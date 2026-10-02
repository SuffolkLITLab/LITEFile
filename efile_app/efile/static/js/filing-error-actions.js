// The API supplies local edit links. Keep upstream/user text out of HTML.
window.FilingErrorActions = {
    render(id, actions = []) {
        const list = document.getElementById(id);
        if (!list) return;
        list.replaceChildren();
        for (const action of Array.isArray(actions) ? actions : []) {
            if (typeof action.url !== "string" || !action.url.startsWith("/jurisdiction/")) continue;
            const item = document.createElement("li");
            const message = document.createElement("span");
            message.textContent = `${action.message || ""} `;
            const link = document.createElement("a");
            link.href = action.url;
            link.textContent = action.label || gettext("Edit this field");
            item.append(message, link);
            list.appendChild(item);
        }
        list.hidden = list.children.length === 0;
    }
};