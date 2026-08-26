/**
 * Shared filing-payload construction.
 *
 * The review page and the payment page each build the exact same `efile_data`
 * blob for the EFSP -- the payment page to quote fees, the review page to quote
 * fees and to submit. These functions were duplicated verbatim in payment.js and
 * review.js; a fix applied to one and not the other produced a fee quote that
 * disagreed with the filing, so they live here once.
 *
 * Mixed into each page's `FilingHandler` with Object.assign, so `this` still
 * refers to the host handler and page-specific hooks (`setFeesState`,
 * `setSubmissionState`) resolve normally.
 *
 * Depends on the page-level globals `Messages`, `apiUtils`, and `gettext`.
 */
/**
 * Normalise a filing component to its bare code.
 *
 * The upload page stores the selection as `{id, name}` on the file record while
 * the durable draft stores a plain code string, so both shapes reach here. Note
 * `typeof null === "object"`, hence the explicit truthiness check -- an older
 * session with `filing_component: null` would otherwise throw on `.id`.
 *
 * @param {Object|string|null|undefined} value
 * @returns {string} the code, or "" when there isn't one
 */
function componentCode(value) {
    if (value && typeof value === "object") {
        return value.id || value.code || "";
    }
    return value || "";
}

/**
 * Convert the service codes stored on a FilingDocument into the object shape
 * expected by the EFSP proxy.
 *
 * @param {Array<string|Object>|null|undefined} services
 * @returns {Array<{code: string}>}
 */
function optionalServicesForPayload(services) {
    if (!Array.isArray(services)) return [];
    return services
        .map((service) => {
            const code = service && typeof service === "object" ? service.code : service;
            return String(code || "").trim();
        })
        .filter(Boolean)
        .map((code) => ({
            code
        }));
}

const FilingPayload = {
    userDataFromCaseData(caseData) {
        const filer = (caseData.filing_parties || []).find((party) => party.role === "filer") || {};
        const fullName = [filer.first_name, filer.middle_name, filer.last_name]
            .filter(Boolean)
            .join(" ") || [caseData.petitioner_first_name, caseData.petitioner_last_name].filter(Boolean).join(" ");
        return {
            fullName,
            address: filer.address_line_1 || caseData.petitioner_address || "",
            addressLine2: filer.address_line_2 || "",
            city: filer.city || "",
            state: filer.state || "",
            zip: filer.zip_code || "",
            email: filer.email || caseData.petitioner_email || "",
            phone: filer.phone || caseData.petitioner_phone || ""
        };
    },

    partyFromDraft(party) {
        return {
            party_type: party.party_type,
            name: {
                first: party.first_name || party.organization_name || "",
                middle: party.middle_name || "",
                last: party.last_name || "",
                suffix: party.suffix || ""
            },
            address: {
                address: party.address_line_1 || "",
                unit: party.address_line_2 || "",
                city: party.city || "",
                state: party.state || "",
                zip: party.zip_code || "",
                country: party.country || "US"
            },
            email: party.email || "",
            phone_number: party.phone || "",
            is_new: !party.external_party_id
        };
    },

    buildEFilingData(userData, caseData, uploadData, paymentAccountID) {
        const nameParts = userData.fullName.split(" ");
        const firstName = nameParts[0] || "";
        const lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";
        const middleName = nameParts.length > 2 ? nameParts.slice(1, -1).join(" ") : "";

        const durableParties = caseData.filing_parties || [];
        const durableFiler = durableParties.find((party) => party.role === "filer");
        const partyType = durableFiler?.party_type || caseData.determined_party_type ||
            caseData.petitioner_party_type || caseData.party_type;

        if (!partyType) {
            throw new Error('Party type could not be determined. This is required for eFiling.');
        }

        // Build user object
        const mainUser = {
            mobile_number: userData.phone,
            phone_number: userData.phone,
            address: {
                address: userData.address,
                unit: userData.addressLine2,
                city: userData.city,
                state: userData.state,
                zip: userData.zip,
                country: "US"
            },
            email: userData.email,
            party_type: partyType,
            date_of_birth: "",
            // The authenticated account is a firm filer, not a self-represented
            // party. Marking the filer as the party makes Tyler reject fees with
            // "Cannot specify self as party for a firm filer."
            is_form_filler: false,
            name: {
                first: firstName,
                middle: middleName,
                last: lastName,
                suffix: ""
            },
            is_new: true
        };

        const users = [mainUser];

        // Add second user if needed for name changes
        if (caseData.new_name_party_type) {
            users.push({
                ...mainUser,
                party_type: caseData.new_name_party_type,
                name: {
                    first: caseData.new_first_name || firstName,
                    middle: caseData.new_middle_name || middleName,
                    last: caseData.new_last_name || lastName,
                    suffix: caseData.new_suffix || ""
                }
            });
        }

        // Add second user if needed for name changes
        const respondentPartyType = caseData.respondent_name_party_type ||
            caseData.respondent_party_type || caseData.defendant_party_type;
        if (respondentPartyType) {
            users.push({
                party_type: respondentPartyType,
                name: {
                    first: caseData.respondent_first_name || caseData.defendant_first_name || "",
                    middle: caseData.respondent_middle_name || caseData.defendant_middle_name || "",
                    last: caseData.respondent_last_name || caseData.defendant_last_name || "",
                    suffix: caseData.respondent_suffix || caseData.defendant_suffix || ""
                },
                is_new: true,
            });
        }

        let other_parties = durableParties
            .filter((party) => party.role !== "filer" && party.party_type)
            .map((party) => this.partyFromDraft(party));

        if (other_parties.length === 0 && caseData.other_first_name && caseData.other_party_type) {
            other_parties.push({
                party_type: caseData.other_party_type,
                name: {
                    first: caseData.other_first_name,
                    last: caseData.other_last_name
                },
                address: {
                    address: caseData.other_address_line_1,
                    unit: caseData.other_address_line_2,
                    city: caseData.other_address_city,
                    state: caseData.other_address_state,
                    zip: caseData.other_address_zip,
                    country: "US"
                },
                email: caseData.other_email,
                phone_number: caseData.other_phone_number,
                is_new: true,
            });
        }

        const efilingData = {
            efile_case_category: caseData.case_category,
            efile_case_type: caseData.case_type,
            efile_case_subtype: caseData.case_subtype,
            previous_case_id: caseData?.previous_case_id,
            docket_number: caseData?.docket_number,
            users,
            other_parties,
            user_started_case: !caseData?.previous_case_id,
            al_court_bundle: [],
            comments_to_clerk: "",
            tyler_payment_id: paymentAccountID,
            // Only sent when a chosen filing type requires it (case_questions
            // asks for it in that case); the EFSP rejects the filing outright
            // if it's required and missing, so leave it out rather than send 0.
            ...(caseData?.amount_in_controversy ? {
                amount_in_controversy: caseData.amount_in_controversy
            } : {}),
            lead_contact: {
                name: {
                    first: firstName,
                    middle: middleName,
                    last: lastName
                },
                email: userData.email
            },
            return_date: ""
        };

        // Add court bundles for documents
        this.addCourtBundles(efilingData, uploadData, caseData, users);

        return efilingData;
    },

    addCourtBundles(efilingData, uploadData, caseData, users) {
        const courtName = caseData.court_name || caseData.court || "";
        // Cook and DuPage require a local attorney/SRL identifier. The code-list
        // entry is the map key; 99500 is the value both courts publish for a
        // self-represented filer. The two courts use different entry codes.
        if (courtName.toLowerCase().includes("cook")) {
            efilingData.cross_references = {
                254500: "99500"
            };
        } else if (courtName.toLowerCase().includes("dupage")) {
            efilingData.cross_references = {
                136524: "99500"
            };
        }

        // Add lead document
        if (uploadData?.files?.lead) {
            const leadBundle = this.createDocumentBundle(
                uploadData.files.lead,
                uploadData.lead_filing_type || caseData.filing_type,
                uploadData.lead_document_type || caseData.document_type,
                uploadData.lead_filing_component || caseData.filing_component,
                users,
                uploadData.lead_filing_type_name || caseData.case_type_name,
                uploadData.lead_document_type_name || "",
                uploadData.lead_cc_email,
                uploadData.lead_requested_optional_services || caseData.optional_services
            );
            efilingData.al_court_bundle.push(leadBundle);
        }

        // Add supporting documents
        if (uploadData?.files?.supporting?.length > 0) {
            uploadData.files.supporting.forEach((doc, index) => {
                const config = uploadData.supporting_documents?.[index] || {};
                const filingComponent = componentCode(config.filing_component) ||
                    componentCode(doc.filing_component);
                const bundle = this.createDocumentBundle(
                    doc,
                    config.filing_type || caseData.filing_type_id,
                    config.document_type || caseData.document_type,
                    filingComponent || caseData.filing_component,
                    users,
                    config.filing_type_name || `Supporting Document ${index + 1}`,
                    config.document_type_name || "",
                    config.cc_email,
                    config.requested_optional_services
                );
                efilingData.al_court_bundle.push(bundle);
            });
        }
    },

    createDocumentBundle(
        doc,
        filingType,
        documentType,
        filingComponent,
        users,
        description,
        docDescription,
        cc_email,
        requestedOptionalServices
    ) {
        const courtesy_copies = cc_email ? [cc_email] : [];
        return {
            proxy_enabled: true,
            filing_type: filingType,
            optional_services: optionalServicesForPayload(requestedOptionalServices),
            due_date: null,
            filing_description: description,
            reference_number: "",
            filing_attorney: "",
            filing_comment: "",
            courtesy_copies: courtesy_copies,
            preliminary_copies: [],
            filing_parties: users.map((_user, index) => `users[${index}]`),
            filing_action: "efile",
            tyler_merge_attachments: false,
            document_type: documentType,
            filing_component: filingComponent,
            filename: doc.name,
            document_description: docDescription,
            data_url: doc.url || doc.s3_url || doc.file_url || doc.download_url
        };
    },

    handleSubmissionResult(result) {
        if (result?.success) {
            Messages.showSuccess(gettext("Filing submitted successfully! You will be redirected to the confirmation page."));
            setTimeout(() => {
                const jurisdiction = apiUtils.getCurrentJurisdiction();
                window.location.href = result.redirect_url || `/jurisdiction/${jurisdiction}/filing-confirmation/`;
            }, 2000);
        } else {
            Messages.showError(result?.error || "An error occurred during submission.");
            this.setSubmissionState(false);
        }
    },

    handleFeesResponse(result) {
        if (result?.success) {
            const response = result.api_response || {};
            const infoElem = document.getElementById("paymentInfo");
            infoElem.replaceChildren();
            const total = document.createElement("p");
            const label = document.createElement("strong");
            label.textContent = gettext("Total");
            total.append(label, `: $${response.feesCalculationAmount?.value || "0.00"}`);
            infoElem.appendChild(total);

            const fees = (response.allowanceCharge || []).filter((fee) => fee.chargeIndicator?.value);
            if (fees.length) {
                const list = document.createElement("ul");
                fees.forEach((fee) => {
                    const item = document.createElement("li");
                    item.textContent = `${fee.allowanceChargeReason?.value || gettext("Court fee")}: $${fee.amount?.value || "0.00"}`;
                    list.appendChild(item);
                });
                infoElem.appendChild(list);
            }
            document.getElementById("paymentSection").removeAttribute("hidden");
        } else {
            Messages.showError(result?.error || "An error occurred when calculating fees.");
        }
        this.setFeesState(false);
    }
};

if (typeof module !== "undefined" && module.exports) {
    module.exports = FilingPayload;
} else {
    window.FilingPayload = FilingPayload;
}