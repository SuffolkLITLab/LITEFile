/**
 * The court question, asked the way the filer's own state is organized.
 *
 * The component holds no court data. Every answer is posted back to
 * /api/dropdowns/court-selector/, which decides against the live court list
 * which questions to ask next, which courts the answers narrow to, and whether
 * one court has been settled on; this file draws whatever comes back. That is
 * what lets Illinois route by county, Massachusetts by department plus a place,
 * and Vermont by Superior Court unit without any of them being written here.
 *
 * Mount it over a court <select> that is already on the page. The select keeps
 * carrying the answer -- it is what the form posts, and what the rest of the
 * screen listens to -- so nothing downstream has to know the selector exists.
 */
(function() {
    const SELECT_THRESHOLD = 8; // more courts than this read better as a dropdown

    function escapeHtml(value) {
        const holder = document.createElement("span");
        holder.textContent = value ?? "";
        return holder.innerHTML;
    }

    function optionsHtml(courts, chosen, placeholder) {
        return [`<option value="">${escapeHtml(placeholder)}</option>`]
            .concat(courts.map((court) => {
                const selected = court.value === chosen ? " selected" : "";
                return `<option value="${escapeHtml(court.value)}"${selected}>${escapeHtml(court.text || court.label)}</option>`;
            }))
            .join("");
    }

    function stepHtml(step) {
        // Where an answer came from the uploaded document rather than the
        // filer, the screen says so, next to the answer it is talking about.
        let source = "";
        if (step.from_document) {
            source = `<small class="court-selector__source">Filled in from your document. Change it if it is wrong.</small>`;
        } else if (step.defaulted && step.default_hint) {
            source = `<small class="court-selector__source">${escapeHtml(step.default_hint)}</small>`;
        }
        const hint = (step.hint ? `<small class="court-selector__hint" id="${step.id}-hint">${escapeHtml(step.hint)}</small>` : "") + source;
        const describedBy = step.hint ? ` aria-describedby="${step.id}-hint"` : "";

        if (step.type === "choice") {
            const choices = step.options.map((option) => `
                <label class="court-selector__choice">
                    <input type="radio" name="court-step-${escapeHtml(step.id)}" value="${escapeHtml(option.value)}"
                           data-step="${escapeHtml(step.id)}"${option.value === step.answer ? " checked" : ""} />
                    <span><strong>${escapeHtml(option.label)}</strong>${option.help ? `<small>${escapeHtml(option.help)}</small>` : ""}</span>
                </label>`).join("");
            return `
                <fieldset class="court-selector__step" data-step="${escapeHtml(step.id)}">
                    <legend>${escapeHtml(step.label)}</legend>
                    ${hint}
                    <div class="court-selector__choices">${choices}</div>
                </fieldset>`;
        }

        if (step.type === "location") {
            const examples = (step.examples || []).map((example) => `
                <button type="button" class="court-selector__example" data-place="${escapeHtml(example)}">${escapeHtml(example)}</button>`).join("");
            return `
                <div class="court-selector__step" data-step="${escapeHtml(step.id)}">
                    <label class="court-selector__label" for="court-step-${escapeHtml(step.id)}">${escapeHtml(step.label)}</label>
                    ${hint}
                    <div class="court-selector__lookup">
                        <input type="text" class="form-control" id="court-step-${escapeHtml(step.id)}"
                               data-location-step="${escapeHtml(step.id)}" value="${escapeHtml(step.answer)}"
                               placeholder="${escapeHtml(step.placeholder)}" autocomplete="off"${describedBy} />
                        <button type="button" class="btn btn-outline-primary" data-find-courts="${escapeHtml(step.id)}">
                            ${escapeHtml(step.button_label || "Find courts")}
                        </button>
                    </div>
                    ${examples ? `<div class="court-selector__examples">${examples}</div>` : ""}
                </div>`;
        }

        return `
            <div class="court-selector__step" data-step="${escapeHtml(step.id)}">
                <label class="court-selector__label" for="court-step-${escapeHtml(step.id)}">${escapeHtml(step.label)}</label>
                ${hint}
                <select class="form-select" id="court-step-${escapeHtml(step.id)}" data-step="${escapeHtml(step.id)}"${describedBy}>
                    <option value="">${escapeHtml(step.placeholder || "Choose one…")}</option>
                    ${groupedOptionsHtml(step)}
                </select>
            </div>`;
    }

    function groupedOptionsHtml(step) {
        // Headings where the courts have them: Cook County's eighty-odd
        // locations are a division and then a courthouse, and reading them as
        // one alphabetical run is what made the old list unusable.
        let html = "";
        let group = null;
        step.options.forEach((option) => {
            const heading = option.group || "";
            if (heading !== group) {
                if (group) html += "</optgroup>";
                if (heading) html += `<optgroup label="${escapeHtml(heading)}">`;
                group = heading;
            }
            const selected = option.value === step.answer ? " selected" : "";
            html += `<option value="${escapeHtml(option.value)}"${selected}>${escapeHtml(option.label)}</option>`;
        });
        return group ? `${html}</optgroup>` : html;
    }

    function answerLabel(step) {
        if (step.type === "location") return step.answer;
        const chosen = step.options.find((option) => option.value === step.answer);
        if (!chosen) return step.answer;
        // Away from its heading, an option needs the name that tells it apart:
        // "Municipal Civil" alone is true of seven Cook County courthouses.
        return chosen.full_label || chosen.label;
    }

    function trailHtml(steps) {
        // An answered question folds down to one line. The filer works down a
        // short list rather than scrolling back up past the questions they have
        // already dealt with -- which matters most on the confirm-filing screen,
        // where the court sits beside three other fields.
        if (!steps.length) return "";
        const rows = steps.map((step) => `
            <button type="button" class="court-selector__answered" data-change="${escapeHtml(step.id)}">
                <span class="court-selector__answered-label">${escapeHtml(step.short_label || step.label)}</span>
                <span class="court-selector__answered-value">${escapeHtml(answerLabel(step))}</span>
                <span class="court-selector__change">Change</span>
            </button>`).join("");
        return `<div class="court-selector__trail">${rows}</div>`;
    }

    function candidatesHtml(matched, chosen) {
        // What the location lookup found. More than one is normal where court
        // jurisdictions overlap, so they are offered rather than guessed between.
        const heading = matched.length === 1 ?
            "The court that serves this place" :
            "Courts that serve this place";
        const items = matched.map((court) => `
            <label class="court-selector__candidate">
                <input type="radio" name="court-candidate" value="${escapeHtml(court.value)}"${court.value === chosen ? " checked" : ""} />
                <span>
                    <strong>${escapeHtml(court.text)}</strong>
                    ${court.matched_name && court.matched_name !== court.text ? `<small>${escapeHtml(court.matched_name)}</small>` : ""}
                    ${court.reason ? `<small>${escapeHtml(court.reason)}</small>` : ""}
                </span>
            </label>`).join("");
        return `<div class="court-selector__candidates"><p class="court-selector__subhead">${escapeHtml(heading)}</p>${items}</div>`;
    }

    function manualHtml(courts, chosen, label, open) {
        // Always offered, never required: a filer who knows their court by name
        // should not have to describe where they live to reach it, and a place
        // the rules cannot resolve has to have a way through.
        if (!courts.length) return "";
        const body = courtListHtml(courts, chosen, "manual");
        return `
            <details class="court-selector__manual"${open ? " open" : ""}>
                <summary>${escapeHtml(label)}</summary>
                <div class="court-selector__manual-body">${body}</div>
            </details>`;
    }

    function courtListHtml(courts, chosen, kind) {
        if (courts.length > SELECT_THRESHOLD) {
            return `<select class="form-select" data-court-list="${kind}">${optionsHtml(courts, chosen, "Choose a court…")}</select>`;
        }
        return courts.map((court) => `
            <label class="court-selector__candidate">
                <input type="radio" name="court-candidate" value="${escapeHtml(court.value)}"${court.value === chosen ? " checked" : ""} />
                <span><strong>${escapeHtml(court.text)}</strong></span>
            </label>`).join("");
    }

    function noteHtml(message) {
        return `<p class="court-selector__note court-selector__note--warn">${escapeHtml(message)}</p>`;
    }

    function locationHtml(data, chosen) {
        const location = data.location;
        const matched = location.matched || [];
        const step = data.steps.find((item) => item.type === "location") || {};
        let html = "";
        if (location.error) {
            html += noteHtml(location.error);
        } else if (location.searched && !matched.length) {
            html += noteHtml(step.no_match_hint);
        } else if (matched.length) {
            html += candidatesHtml(matched, chosen);
        }
        // Only where the lookup is the main way in. Vermont keeps its unit
        // dropdown above, so repeating the same courts here would say nothing.
        if (!step.manual_label) return html;
        const openManually = Boolean(location.searched) && !matched.length;
        return html + manualHtml(data.courts || [], chosen, step.manual_label, openManually);
    }

    function resultHtml(data) {
        const selected = data.selected;
        if (!selected) return "";
        // The answers that led here, so the filer can check the route as well
        // as the court at the end of it.
        const path = (data.path || []).filter(Boolean).join(" › ");
        return `
            <div class="court-selector__result">
                <span class="court-selector__result-label">Court</span>
                <strong>${escapeHtml(selected.text)}</strong>
                ${selected.reason ? `<small>${escapeHtml(selected.reason)}</small>` : ""}
                ${path ? `<small class="court-selector__path">${escapeHtml(path)}</small>` : ""}
            </div>`;
    }

    function extraHtml(data, chosen) {
        if (data.location) return locationHtml(data, chosen);
        // Every routing question is answered and more than one court is still on
        // the table -- the last of the narrowing is the filer's.
        if (data.waiting || (data.courts || []).length < 2) return "";
        return `<p class="court-selector__subhead">Which of these is your court?</p>${courtListHtml(data.courts, chosen, "final")}`;
    }

    function mount(options) {
        const {
            container,
            jurisdiction,
            select,
            nameInput,
            onSelect
        } = options;
        const answers = {};
        let latest = 0;
        let lastSteps = [];
        let expanded = ""; // the answered question the filer reopened
        let lastRender = {
            steps: []
        }; // redrawn as-is when only the folding changes
        // Mounting again over the same element retires the previous mount's
        // listeners, so two selectors can never both answer one click.
        if (container.courtSelectorListeners) container.courtSelectorListeners.abort();
        const listeners = new AbortController();
        container.courtSelectorListeners = listeners;

        function open(step, data) {
            // An unanswered question is always open, and so is one the filer
            // asked to change. A place that matched nothing stays open too:
            // retyping it is the obvious next move, not a click away.
            // A suggested answer is not one the filer gave, so it stays in
            // front of them rather than folding away as settled.
            if (expanded === step.id || !step.answer || step.defaulted) return true;
            if (step.type === "location" && data.location) {
                return Boolean(data.location.searched) && !(data.location.matched || []).length;
            }
            return false;
        }

        function render(data) {
            lastSteps = data.steps || [];
            const chosen = data.selected ? data.selected.value : "";
            // Once there is a court, the questions that produced it fold away
            // and so does everything that was there to choose between: the
            // answer is stated, and "Change" is how the filer goes back to it.
            const settled = Boolean(data.selected) && !expanded && !lastSteps.some((step) => step.defaulted);
            const steps = settled ? [] : lastSteps.filter((step) => open(step, data));
            const answered = settled ?
                lastSteps.filter((step) => step.answer) :
                lastSteps.filter((step) => !open(step, data));
            container.innerHTML = `
                ${steps.length && data.lede ? `<p class="court-selector__lede">${escapeHtml(data.lede)}</p>` : ""}
                ${trailHtml(answered)}
                <div class="court-selector__steps">${steps.map(stepHtml).join("")}</div>
                ${settled ? "" : extraHtml(data, chosen)}
                ${resultHtml(data)}`;
            publish(data.selected, data.courts || []);
        }

        function publish(selected, courts) {
            // The <select> under this component is what the form posts, so it
            // carries whatever has been settled on -- and only that, so a form
            // submitted mid-question cannot carry a court nobody chose.
            const before = select.value;
            const pool = selected ? [selected] : courts;
            select.innerHTML = optionsHtml(pool, selected ? selected.value : "", "");
            select.value = selected ? selected.value : "";
            if (nameInput) nameInput.value = selected ? selected.text : "";
            // Only when the court actually changed: everything downstream --
            // case categories, types, fees -- is refetched off this event.
            if (select.value !== before) select.dispatchEvent(new Event("change", {
                bubbles: true
            }));
            if (onSelect) onSelect(selected);
        }

        async function refresh() {
            const request = ++latest;
            const query = new URLSearchParams({
                jurisdiction,
                answers: JSON.stringify(answers)
            });
            container.setAttribute("aria-busy", "true");
            try {
                const response = await fetch(`/api/dropdowns/court-selector/?${query}`, {
                    headers: {
                        "X-CSRFToken": apiUtils.getCSRFToken()
                    },
                });
                const result = await response.json();
                if (request !== latest) return; // a later answer already went out
                if (!response.ok || !result.success) throw new Error(result.error || "Could not load the court questions.");
                if (!result.data.available) throw new Error("This jurisdiction no longer has guided court questions. Reload the page.");
                lastRender = result.data;
                render(result.data);
            } catch (error) {
                if (request === latest) {
                    container.innerHTML = `<p class="court-selector__note court-selector__note--warn">${escapeHtml(error.message)}</p>`;
                }
            } finally {
                container.removeAttribute("aria-busy");
            }
        }

        function answerStep(stepId, value) {
            answers[stepId] = value;
            expanded = "";
            // Two steps that are alternatives to each other are two ways of
            // naming one court, so answering either clears the other rather
            // than leaving a stale answer to disagree with it.
            (lastSteps || []).forEach((step) => {
                if (step.alternative_to === stepId || (step.id === stepId && step.alternative_to)) {
                    delete answers[step.alternative_to === stepId ? step.id : step.alternative_to];
                }
            });
            // A different route means a different court: whatever was chosen
            // under the old answer cannot survive it.
            delete answers.court;
            refresh();
        }

        container.addEventListener("change", (event) => {
            const target = event.target;
            if (target.name === "court-candidate" || target.dataset.courtList) {
                answers.court = target.value;
                refresh();
                return;
            }
            const stepId = target.dataset.step;
            if (stepId) answerStep(stepId, target.value);
        }, {
            signal: listeners.signal
        });

        container.addEventListener("click", (event) => {
            const reopen = event.target.closest("[data-change]");
            if (reopen) {
                expanded = reopen.dataset.change;
                render(lastRender);
                return;
            }
            const findButton = event.target.closest("[data-find-courts]");
            if (findButton) {
                const input = container.querySelector(`[data-location-step="${findButton.dataset.findCourts}"]`);
                answerStep(findButton.dataset.findCourts, input ? input.value.trim() : "");
                return;
            }
            const example = event.target.closest(".court-selector__example");
            if (example) {
                const input = container.querySelector("[data-location-step]");
                if (input) {
                    input.value = example.dataset.place;
                    answerStep(input.dataset.locationStep, example.dataset.place);
                }
            }
        }, {
            signal: listeners.signal
        });

        container.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && event.target.dataset.locationStep) {
                // Enter in a lookup box means "find", not "submit the filing".
                event.preventDefault();
                answerStep(event.target.dataset.locationStep, event.target.value.trim());
            }
        }, {
            signal: listeners.signal
        });

        return {
            /** Draw the first questions, picking up a court already chosen. */
            async start(courtCode, guessedCourt) {
                const query = new URLSearchParams({
                    jurisdiction
                });
                if (courtCode) query.set("court", courtCode);
                if (guessedCourt) query.set("guessed_court", guessedCourt);
                const response = await fetch(`/api/dropdowns/court-selector/?${query}`, {
                    headers: {
                        "X-CSRFToken": apiUtils.getCSRFToken()
                    },
                });
                const result = await response.json();
                if (!response.ok || !result.success || !result.data.available) return false;
                (result.data.steps || []).forEach((step) => {
                    if (step.answer) answers[step.id] = step.answer;
                });
                if (result.data.selected) answers.court = result.data.selected.value;
                lastRender = result.data;
                render(result.data);
                return true;
            },
        };
    }

    window.courtSelector = {
        mount
    };
})();