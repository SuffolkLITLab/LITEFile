(function() {
    function mount({
        jurisdiction,
        existingCase,
        applyPath
    }) {
        const dialog = document.getElementById("code-search-dialog");
        const open = document.getElementById("open-code-search");
        if (!dialog || !open) return;
        const query = document.getElementById("code-search-query");
        const status = document.getElementById("code-search-status");
        const results = document.getElementById("code-search-results");
        const apply = document.getElementById("apply-code-search");
        const more = document.getElementById("code-search-more");
        const suggestions = document.getElementById("code-search-suggestions");
        const purpose = document.getElementById("code-search-purpose");
        const stage = document.getElementById("code-search-stage");
        const documentKind = document.getElementById("code-search-document");
        const postalCode = document.getElementById("code-search-zip");
        if (jurisdiction === "illinois") {
            document.getElementById("code-search-zip-filter").hidden = false;
            document.getElementById("code-search-zip-help").hidden = false;
        }
        postalCode.addEventListener("input", () => {
            invalidate();
            clearResults();
            timer = setTimeout(() => search(), 350);
        });
        const caseFilters = document.getElementById("code-search-case-filters");
        let caseTopic = "";
        let caseChoices = {};
        let caseFilterSchema = "";
        const caseFilterValues = () => ({
            case_topic: caseTopic,
            case_filters: JSON.stringify(caseChoices)
        });
        caseFilters.addEventListener("change", event => {
            const key = event.target.dataset.caseFacet;
            if (key === "topic") {
                caseTopic = event.target.value;
                caseChoices = {};
            } else if (key) {
                if (event.target.value) caseChoices[key] = event.target.value;
                else delete caseChoices[key];
            }
            search();
        });

        function resetCaseFilters() {
            caseTopic = "";
            caseChoices = {};
            caseFilterSchema = "";
            caseFilters.hidden = true;
        }
        const filters = [purpose, stage, documentKind];
        let generation = 0;
        let controller;
        let timer;
        let selected = null;
        let offset = 0;
        let applying = false;

        function invalidate() {
            generation += 1;
            controller?.abort();
            controller = null;
            clearTimeout(timer);
            selected = null;
            apply.disabled = true;
            more.hidden = true;
        }

        async function request(params, signal) {
            const response = await fetch(`/api/filing-code-search/?${new URLSearchParams({
                jurisdiction, zip: postalCode.value.trim(), existing_case: stage.value, purpose: purpose.value, document: documentKind.value, grouped: "true", ...caseFilterValues(), ...params,
            })}`, {
                signal,
                headers: {
                    Accept: "application/json"
                }
            }).catch(error => {
                if (error.name === "AbortError") throw error;
                const unavailable = new Error(gettext("Code search could not be loaded. Try again shortly."));
                unavailable.retryable = true;
                throw unavailable;
            });
            if (!response.headers.get("content-type")?.includes("application/json")) {
                const error = new Error(gettext("Code search could not be loaded. Refresh the page and try again."));
                error.retryable = response.status >= 500;
                throw error;
            }
            const data = await response.json();
            if (!response.ok) {
                const error = new Error(data.error || gettext("Code search could not be loaded. Try again."));
                error.retryable = response.status === 503;
                throw error;
            }
            return data;
        }

        function element(tag, text, className) {
            const node = document.createElement(tag);
            if (text) node.textContent = text;
            if (className) node.className = className;
            return node;
        }

        function addSearchContext(data, target) {
            const meanings = data.concepts || [];
            const reason = data.match_reason?.kind === "related_concept" ? data.match_reason : null;
            if (!reason && !meanings.some(item => item.text)) return null;
            const details = element("details", "", reason ? "code-search__match-reason" : "code-search__concept-info");
            details.append(element("summary", reason ? gettext("Why is this result shown?") : gettext("About this filing type")));
            target.append(details);
            for (const concept of meanings.filter(item => item.text)) {
                const definition = element("div", "", "code-search__meaning");
                let scope = gettext("General meaning");
                if (concept.scope === "county") scope = interpolate(gettext("Meaning in %(name)s County"), {
                    name: concept.scope_name
                }, true);
                else if (concept.scope !== "general") scope = interpolate(gettext("Meaning in %(name)s"), {
                    name: concept.scope_name
                }, true);
                definition.append(element("p", `${concept.label} — ${scope}: ${concept.text}`));
                if (concept.source) {
                    const source = element("a", gettext("About this concept"));
                    source.href = concept.source;
                    source.target = "_blank";
                    source.rel = "noopener noreferrer";
                    definition.append(source);
                }
                details.append(definition);
            }
            if (!reason) return details;
            const labels = meanings.filter(item => reason.concepts.includes(item.key)).map(item => item.label);
            const text = interpolate(gettext('Your search for “%(query)s” relates to %(concepts)s. This filing name or its associated case information deals with similar concepts.'), {
                query: reason.query,
                concepts: labels.join(", ")
            }, true);
            details.insertBefore(element("p", text), details.children[1] || null);
            return details;
        }

        function addFacetSummary(data, target) {
            const facets = data.facets || {};
            const purposes = {
                starting: gettext("Starting a claim"),
                responding: gettext("Responding to a claim"),
                either: gettext("Either side")
            };
            const documents = {
                main: gettext("Main document"),
                attachment: gettext("Attachment / exhibit")
            };
            const labels = [purposes[facets.purpose], documents[facets.document]].filter(Boolean);
            const contexts = data.case_contexts || [];
            if (contexts.length) {
                const context = data.case_context_count > 1 ?
                    interpolate(gettext("%(count)s case types, including %(context)s"), {
                        context: contexts[0],
                        count: data.case_context_count
                    }, true) : contexts[0];
                labels.unshift(context);
            }
            if (labels.length) {
                const summary = element("p", labels.join(" · "), "code-search__meta");
                summary.title = summary.textContent;
                target.append(summary);
            }
        }

        function addResult(path, target = results, group = null) {
            const row = element("div", "", group ? "code-search__result code-search__path-choice" : "code-search__result");
            const label = element("label");
            const radio = document.createElement("input");
            radio.type = "radio";
            radio.name = "code-search-result";
            radio.value = path.id;
            radio.disabled = Boolean(path.unavailable);
            const choiceName = group ? (path.case_context || path.case_type.name) : path.filing_type.name;
            label.append(radio, element("span", choiceName));
            row.append(label);
            if (!group) {
                addFacetSummary(path, row);
                row.append(element("p", `${path.case_context || path.case_type.name} · ${path.court.name}`, "code-search__meta"));
            } else if (path.filing_type.name.toLowerCase() !== group.name.toLowerCase()) {
                row.append(element("p", path.filing_type.name, "code-search__variant"));
            }
            if (group && path.case_description) {
                const description = element("p", path.case_description, "code-search__case-description");
                description.id = `code-search-description-${path.id}`;
                radio.setAttribute("aria-describedby", description.id);
                row.append(description);
            }
            const details = element("details");
            details.append(element("summary", group ? gettext("Details") : gettext("Filing path")));
            if (group) {
                addFacetSummary(path, details);
            }
            if (path.explanation) details.append(element("p", path.explanation));
            if (path.case_guidance?.source) {
                const source = element("a", gettext("About this case type"));
                source.href = path.case_guidance.source;
                source.target = "_blank";
                source.rel = "noopener noreferrer";
                details.append(source);
            }
            if (path.explanation_source) {
                const source = element("a", gettext("Court information"));
                source.href = path.explanation_source;
                source.target = "_blank";
                source.rel = "noopener noreferrer";
                details.append(source);
            }
            const list = element("ol", "", "code-search__path");
            const facets = [
                ["court", gettext("Court")],
                ["case_category", gettext("Case category")],
                ["case_type", gettext("Case type")],
                ["filing_type", gettext("Filing type")],
            ];
            facets.forEach(([key, title]) => list.append(element("li", `${title}: ${path[key].name}`)));
            details.append(list);
            row.append(details);
            if (path.unavailable) row.append(element("p", path.unavailable));
            radio.addEventListener("change", () => {
                selected = path;
                apply.disabled = false;
                for (const item of results.querySelectorAll("details")) item.open = !group && item === details;
            });
            target.append(row);
        }

        function addGroup(group, searchText) {
            const row = element("div", "", "code-search__result code-search__group");
            row.append(element("h3", group.name));
            let info = addSearchContext(group, row);
            addFacetSummary(group, row);
            if (!info && (group.case_contexts?.length || group.variants.length > 1)) {
                info = element("details");
                info.append(element("summary", gettext("About this filing type")));
                row.append(info);
            }
            if (group.case_contexts?.length) {
                info.append(element("p", gettext("Used in these case types:")));
                const contexts = element("ul");
                for (const context of group.case_contexts) {
                    const item = element("li");
                    const option = group.case_context_options?.find(candidate => candidate.label === context);
                    if (option) {
                        const link = element("button", context, "btn btn-link code-search__context-link");
                        link.type = "button";
                        link.addEventListener("click", () => {
                            contextKey = option.key;
                            contextLabel.textContent = interpolate(gettext("Case type: %(name)s"), {
                                name: context
                            }, true);
                            contextChoice.hidden = false;
                            loadCourts();
                        });
                        item.append(link);
                    } else item.textContent = context;
                    contexts.append(item);
                }
                info.append(contexts);
                if (group.case_context_count > group.case_contexts.length) {
                    info.append(element("p", gettext("More case types are available. Choose a court to see its full filing paths.")));
                }
            }
            if (group.variants.length > 1) {
                info.append(element("p", gettext("Also listed as:") + " " + group.variants.slice(1).join("; ")));
            }
            const choose = element("button", gettext("Choose a court"), "btn btn-outline-primary");
            choose.type = "button";
            choose.setAttribute("aria-label", interpolate(gettext("Choose a court for %(name)s"), {
                name: group.name
            }, true));
            const panel = element("div", "", "code-search__group-panel");
            panel.hidden = true;
            const message = element("p");
            message.setAttribute("role", "status");
            const contextChoice = element("div");
            contextChoice.hidden = true;
            const contextLabel = element("span");
            const resetContext = element("button", gettext("Show all case types"), "btn btn-link");
            resetContext.type = "button";
            contextChoice.append(contextLabel, resetContext);
            const label = element("label", gettext("Court"));
            const court = element("select", "", "form-select form-select-sm");
            court.id = `code-search-court-${group.key}`;
            label.htmlFor = court.id;
            const paths = element("div");
            const next = element("button", gettext("Show more paths in this court"), "btn btn-link");
            next.type = "button";
            next.hidden = true;
            const courtControls = element("div", "", "code-search__court-controls");
            courtControls.append(label, court, message);
            panel.append(contextChoice, courtControls, paths, next);
            row.append(choose, panel);
            results.append(row);
            const token = generation;
            const signal = controller.signal;
            let detailGeneration = 0;
            let courtGeneration = 0;
            let contextKey = "";
            let pathOffset = 0;

            async function loadPaths(append = false) {
                const detailToken = ++detailGeneration;
                if (!append) {
                    pathOffset = 0;
                    paths.replaceChildren();
                    selected = null;
                    apply.disabled = true;
                    for (const input of results.querySelectorAll('input[name="code-search-result"]')) input.checked = false;
                }
                next.hidden = true;
                if (!court.value) {
                    message.textContent = gettext("Choose a court to see its case types and filing paths.");
                    return;
                }
                message.textContent = gettext("Loading filing paths…");
                try {
                    const data = await request({
                        q: searchText,
                        group: group.key,
                        context: contextKey,
                        court: court.value,
                        offset: pathOffset
                    }, signal);
                    if (token !== generation || detailToken !== detailGeneration || !dialog.open) return;
                    for (const path of data.results) addResult(path, paths, group);
                    pathOffset += data.results.length;
                    message.textContent = data.total ? gettext("Choose your case type.") : gettext("No matching paths in this court.");
                    next.hidden = pathOffset >= data.total || pathOffset >= 10000;
                } catch (error) {
                    if (token === generation && detailToken === detailGeneration && error.name !== "AbortError") message.textContent = error.message;
                }
            }

            court.addEventListener("change", () => loadPaths());
            next.addEventListener("click", () => loadPaths(true));
            async function loadCourts() {
                const courtToken = ++courtGeneration;
                ++detailGeneration;
                paths.replaceChildren();
                selected = null;
                apply.disabled = true;
                next.hidden = true;
                for (const input of results.querySelectorAll('input[name="code-search-result"]')) input.checked = false;
                const previousCourt = court.value;
                choose.disabled = true;
                panel.hidden = false;
                court.disabled = true;
                message.textContent = gettext("Loading courts…");
                try {
                    const data = await request({
                        q: searchText,
                        group: group.key,
                        context: contextKey
                    }, signal);
                    if (token !== generation || courtToken !== courtGeneration || !dialog.open) return;
                    court.replaceChildren(element("option", gettext("Choose a court")));
                    court.firstElementChild.value = "";
                    const preferred = previousCourt || document.getElementById("court_code")?.value;
                    const prioritized = [];
                    for (const item of data.courts) {
                        if (item.code === preferred) prioritized.unshift(item);
                        else prioritized.push(item);
                    }
                    for (const item of prioritized) {
                        const option = element("option", item.name);
                        option.value = item.code;
                        court.append(option);
                    }
                    if (prioritized[0]?.code === preferred) court.value = preferred;
                    court.disabled = false;
                    choose.hidden = true;
                    court.focus();
                    await loadPaths();
                } catch (error) {
                    if (token === generation && courtToken === courtGeneration && error.name !== "AbortError") {
                        message.textContent = error.message;
                        choose.disabled = false;
                    }
                }
            }
            choose.addEventListener("click", loadCourts);
            resetContext.addEventListener("click", () => {
                contextKey = "";
                contextChoice.hidden = true;
                loadCourts();
            });
        }

        function clearResults() {
            results.querySelectorAll(".code-search__result").forEach(row => row.remove());
        }

        function facetSelect(facet) {
            const wrapper = element("div");
            const id = `code-search-facet-${facet.key}`;
            const label = element("label", facet.label);
            label.htmlFor = id;
            const select = element("select", "", "form-select form-select-sm");
            select.id = id;
            select.dataset.caseFacet = facet.key;
            const any = element("option", facet.key === "topic" ? gettext("All case areas") : gettext("Any / not sure"));
            any.value = facet.key === "topic" ? "all" : "";
            select.append(any);
            for (const choice of facet.options) {
                const option = element("option", choice.label);
                option.value = choice.value;
                select.append(option);
            }
            select.value = facet.key === "topic" ? caseTopic || "all" : caseChoices[facet.key] || "";
            wrapper.append(label, select);
            return wrapper;
        }

        function facetRadios(facet) {
            const fieldset = element("fieldset");
            fieldset.append(element("legend", facet.label));
            for (const choice of [{
                    value: "",
                    label: gettext("Any")
                }, ...facet.options]) {
                const label = element("label");
                const input = element("input");
                input.type = "radio";
                input.name = `code-search-${facet.key}`;
                input.id = `code-search-${facet.key}-${choice.value || "any"}`;
                input.dataset.caseFacet = facet.key;
                input.value = choice.value;
                input.checked = choice.value === (caseChoices[facet.key] || "");
                label.append(input, document.createTextNode(choice.label));
                fieldset.append(label);
            }
            return fieldset;
        }

        function renderCaseFilters(data) {
            caseTopic = data.case_topic || "";
            caseFilters.hidden = !data.case_topics.length && !Object.keys(caseChoices).length;
            const schema = JSON.stringify([caseTopic, data.case_topics, data.case_facets]);
            if (schema === caseFilterSchema) return;
            caseFilterSchema = schema;
            const focused = caseFilters.contains(document.activeElement) ? document.activeElement.id : "";
            caseFilters.replaceChildren();
            caseFilters.append(facetSelect({
                key: "topic",
                label: gettext("Case area"),
                options: data.case_topics
            }));
            for (const facet of data.case_facets) {
                caseFilters.append(facet.control === "select" ? facetSelect(facet) : facetRadios(facet));
                if (facet.help) {
                    const help = element("details", "", "code-search__amount-help");
                    help.append(element("summary", gettext("About claim amounts")), element("p", facet.help));
                    if (facet.source) {
                        const source = element("a", gettext("Court guidance"));
                        source.href = facet.source;
                        source.target = "_blank";
                        source.rel = "noopener noreferrer";
                        help.append(source);
                    }
                    caseFilters.append(help);
                }
            }
            if (data.case_facets.length) caseFilters.append(element("p", gettext("Options with unspecified details stay included."), "code-search__meta"));
            if (focused) document.getElementById(focused)?.focus();
        }

        function showSearchSummary(data) {
            if (data.case_topics) renderCaseFilters(data);
            const template = data.groups ?
                gettext("Showing %(shown)s of %(total)s filing types.") :
                gettext("Showing %(shown)s of %(total)s matching paths.");
            status.textContent = data.total ? interpolate(template, {
                    shown: offset,
                    total: data.total
                }, true) :
                gettext("No matching paths. Try fewer words, another term, or the court lists.");
            if (data.location_counties?.length) status.textContent += " " + interpolate(gettext("Counties: %(names)s."), {
                names: data.location_counties.join(", ")
            }, true);
            if (data.corrected_terms.length) status.textContent += " " + gettext("Similar spellings were included.");
            if (data.stale) status.textContent += " " + gettext("These lists may be out of date. We will check your choice with the court.");
            more.hidden = offset >= data.total || offset >= 10000;
        }

        async function search(append = false) {
            const text = query.value.trim();
            if (!append) {
                invalidate();
                offset = 0;
                clearResults();
            }
            suggestions.hidden = Boolean(text);
            results.hidden = !text;
            if (!text) {
                status.textContent = "";
                return;
            }
            const token = generation;
            controller ||= new AbortController();
            more.hidden = true;
            status.textContent = gettext("Searching filing paths…");
            try {
                const data = await request({
                    q: text,
                    offset
                }, controller.signal);
                if (token !== generation || !dialog.open) return;
                if (data.groups) data.groups.forEach(group => addGroup(group, text));
                else data.results.forEach(path => addResult(path));
                offset += (data.groups || data.results).length;
                showSearchSummary(data);
            } catch (error) {
                if (token === generation && error.name !== "AbortError") {
                    status.textContent = error.message;
                    if (error.retryable) {
                        status.textContent += " " + gettext("We will try again shortly.");
                        timer = setTimeout(() => search(append), 10000);
                    }
                }
            }
        }

        open.disabled = false;
        open.addEventListener("click", () => {
            stage.value = existingCase();
            dialog.showModal();
            query.focus();
            search();
        });
        filters.forEach(filter => filter.addEventListener("change", () => search()));
        query.addEventListener("input", () => {
            resetCaseFilters();
            invalidate();
            clearResults();
            status.textContent = gettext("Searching filing paths…");
            if (!query.value.trim()) search();
            else timer = setTimeout(() => search(), 250);
        });
        suggestions.addEventListener("click", event => {
            const button = event.target.closest("[data-code-query]");
            if (!button) return;
            query.value = button.dataset.codeQuery;
            query.focus();
            search();
        });
        query.addEventListener("keydown", event => {
            if (event.key === "Enter") {
                event.preventDefault();
                search();
            }
        });
        more.addEventListener("click", () => search(true));

        function close() {
            if (!applying) dialog.close();
        }
        ["close-code-search", "cancel-code-search"].forEach(id => document.getElementById(id).addEventListener("click", close));
        dialog.addEventListener("cancel", event => {
            if (applying) event.preventDefault();
        });
        dialog.addEventListener("keydown", event => {
            if (event.key !== "Tab") return;
            const controls = Array.from(dialog.querySelectorAll("button, input, select, a[href], summary, [tabindex]"))
                .filter(node => node.tabIndex >= 0 && !node.matches(":disabled") && node.getClientRects().length);
            const first = controls[0];
            const last = controls[controls.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
            }
        });
        dialog.addEventListener("close", () => {
            invalidate();
            open.focus();
        });
        apply.addEventListener("click", async () => {
            if (!selected || applying) return;
            applying = true;
            apply.disabled = true;
            query.disabled = true;
            filters.forEach(filter => filter.disabled = true);
            results.inert = true;
            more.disabled = true;
            status.textContent = gettext("Checking this path with the court…");
            try {
                const data = await request({
                    path_id: selected.id
                });
                await applyPath(data.path);
                dialog.close();
            } catch (error) {
                status.textContent = error.message;
                apply.disabled = false;
            } finally {
                applying = false;
                query.disabled = false;
                filters.forEach(filter => filter.disabled = false);
                results.inert = false;
                more.disabled = false;
            }
        });
    }
    window.filingCodeSearch = {
        mount
    };
})();