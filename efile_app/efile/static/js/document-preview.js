/* PDF.js is served locally; document bytes stay on the authenticated app origin. */
(() => {
    const assetScript = document.querySelector("script[data-pdf-library]");
    let modules;

    function loadModules() {
        if (!modules) {
            modules = import(assetScript.dataset.pdfLibrary).then(async (pdfjs) => {
                pdfjs.GlobalWorkerOptions.workerSrc = assetScript.dataset.pdfWorker;
                globalThis.pdfjsLib = pdfjs;
                const components = await import(assetScript.dataset.pdfViewer);
                return {
                    pdfjs,
                    components
                };
            });
        }
        return modules;
    }

    async function openPreview(details) {
        if (!details.open || details.dataset.loaded) return;
        details.dataset.loaded = "true";
        const status = details.querySelector("[data-pdf-status]");
        status.textContent = gettext("Loading PDF…");
        let task;
        try {
            const {
                pdfjs,
                components
            } = await loadModules();
            const container = details.querySelector("[data-pdf-url]");
            const eventBus = new components.EventBus();
            const linkService = new components.PDFLinkService({
                eventBus
            });
            const viewer = new components.PDFViewer({
                container,
                eventBus,
                linkService,
                textLayerMode: 1,
                annotationMode: pdfjs.AnnotationMode.ENABLE,
                enableScripting: false,
            });
            linkService.setViewer(viewer);
            task = pdfjs.getDocument({
                url: container.dataset.pdfUrl,
                isEvalSupported: false,
                cMapUrl: assetScript.dataset.pdfResources + "cmaps/",
                cMapPacked: true,
                standardFontDataUrl: assetScript.dataset.pdfResources + "standard_fonts/",
                wasmUrl: assetScript.dataset.pdfResources + "wasm/",
                disableRange: true,
                disableAutoFetch: true,
            });
            const pdf = await task.promise;
            viewer.setDocument(pdf);
            linkService.setDocument(pdf);
            const pageInput = details.querySelector("[data-pdf-page]");
            pageInput.max = pdf.numPages;
            details.querySelector("[data-pdf-page-count]").textContent = interpolate(gettext("of %s"), [pdf.numPages]);
            eventBus.on("pagesinit", () => {
                viewer.currentScaleValue = "page-width";
                for (let index = 0; index < pdf.numPages; index++) {
                    const pageRegion = viewer.getPageView(index).div;
                    pageRegion.removeAttribute("data-l10n-id");
                    pageRegion.removeAttribute("data-l10n-args");
                    pageRegion.setAttribute("aria-label", interpolate(gettext("%s, page %s"), [container.getAttribute("aria-label"), index + 1]));
                }
            });
            eventBus.on("pagerendered", (event) => {
                status.textContent = event.error ? gettext("This page did not load. Download the PDF to view it.") : "";
                if (!event.error) details.dataset.rendered = "true";
            });
            eventBus.on("pagechanging", (event) => {
                pageInput.value = event.pageNumber;
            });
            details.querySelector(".document-preview__toolbar").hidden = false;
            pageInput.addEventListener("change", () => {
                const page = Number(pageInput.value);
                if (Number.isInteger(page) && page >= 1 && page <= pdf.numPages) viewer.currentPageNumber = page;
            });
            details.querySelector("[data-pdf-previous]").addEventListener("click", () => viewer.previousPage());
            details.querySelector("[data-pdf-next]").addEventListener("click", () => viewer.nextPage());
            details.querySelector("[data-pdf-zoom-in]").addEventListener("click", () => viewer.increaseScale());
            details.querySelector("[data-pdf-zoom-out]").addEventListener("click", () => viewer.decreaseScale());
            details.addEventListener("toggle", () => {
                if (details.open) viewer.update();
            });
        } catch (error) {
            console.warn("PDF preview failed", error.message);
            if (task) await task.destroy();
            modules = undefined;
            delete details.dataset.loaded;
            status.textContent = gettext("The PDF did not load. Download it or close and reopen this view.");
        }
    }
    document.querySelectorAll("[data-pdf-preview]").forEach((details) => {
        details.addEventListener("toggle", () => openPreview(details));
    });
})();