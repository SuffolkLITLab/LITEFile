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

const FilingPayload = {
    buildEFilingData(userData, caseData, uploadData, paymentAccountID) {
        const nameParts = userData.fullName.split(" ");
        const firstName = nameParts[0] || "";
        const lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";
        const middleName = nameParts.length > 2 ? nameParts.slice(1, -1).join(" ") : "";

        const partyType = caseData.determined_party_type || caseData.petitioner_party_type || caseData.party_type;

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
        if (caseData.respondent_name_party_type) {
            users.push({
                party_type: caseData.respondent_name_party_type,
                name: {
                    first: caseData.respondent_first_name || "",
                    middle: caseData.respondent_middle_name || "",
                    last: caseData.respondent_last_name || "",
                    suffix: caseData.respondent_suffix || ""
                },
                is_new: true,
            });
        }

        let other_parties = [];

        if (caseData.other_first_name && caseData.other_party_type) {
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
        if (courtName.toLowerCase().includes("cook") || courtName.toLowerCase().includes("dupage")) {
            efilingData.cross_references = {
                254500: "254500"
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
                uploadData.lead_cc_email
            );
            efilingData.al_court_bundle.push(leadBundle);
        }

        // Add supporting documents
        if (uploadData?.files?.supporting?.length > 0) {
            uploadData.files.supporting.forEach((doc, index) => {
                const config = uploadData.supporting_documents?.[index] || {};
                const filingComponent = componentCode(config.filing_component)
                    || componentCode(doc.filing_component);
                const bundle = this.createDocumentBundle(
                    doc,
                    config.filing_type || caseData.filing_type_id,
                    config.document_type || caseData.document_type,
                    filingComponent || caseData.filing_component,
                    users,
                    config.filing_type_name || `Supporting Document ${index + 1}`,
                    config.document_type_name || "",
                    config.cc_email
                );
                efilingData.al_court_bundle.push(bundle);
            });
        }
    },

    createDocumentBundle(doc, filingType, documentType, filingComponent, users, description, docDescription, cc_email) {
        if (cc_email) {
            courtesy_copies = [cc_email]
        } else {
            courtesy_copies = []
        }
        return {
            proxy_enabled: true,
            filing_type: filingType,
            optional_services: [],
            due_date: null,
            filing_description: description,
            reference_number: "",
            filing_attorney: "",
            filing_comment: "",
            courtesy_copies: courtesy_copies,
            preliminary_copies: [],
            filing_parties: users.length === 1 ? ["users[0]"] : ["users[0]", "users[1]"],
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
            let htmlStr = `
            <strong>Total</strong>: $${result.api_response.feesCalculationAmount.value}
            
            <ul>
            `;
            for (let specificFee of result.api_response.allowanceCharge) {
                if (specificFee.chargeIndicator.value) {
                    htmlStr += `<li><em>${specificFee.allowanceChargeReason.value}</em>:  $${specificFee.amount.value}</li>`;
                }
            }
            htmlStr += "</ul>";

            let infoElem = document.getElementById("paymentInfo");
            infoElem.innerHTML = htmlStr;
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
