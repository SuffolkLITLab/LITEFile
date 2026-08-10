(function() {
    const form = document.getElementById("case-questions-form");
    if (!form) return;
    const children = form.querySelectorAll('input[name="has_children"]');
    const childCountCard = form.querySelector('[data-question="child_count"]');
    const childCount = form.elements.namedItem("child_count");
    if (!children.length || !childCountCard || !childCount) return;

    function updateChildCount() {
        const selected = form.querySelector('input[name="has_children"]:checked');
        const show = selected?.value === "true";
        childCountCard.hidden = !show;
        childCount.required = show;
        if (!show) childCount.value = "";
    }

    children.forEach((radio) => radio.addEventListener("change", updateChildCount));
    updateChildCount();
})();