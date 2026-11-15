
---

> **Status: Template (placeholder text).** This is a starting template, not an adopted policy — bracketed placeholders must be filled, the data inventory below tailored to the actual deployment, and the result legally reviewed before any release relies on it. BS-specific tailoring notes are marked **[BS note]**.

## Privacy Policy

*Last Updated: [Date]*

### 1. Our Commitment to Privacy

At [Company Name], we are committed to respecting your privacy and protecting your personal information. This Privacy Policy details how we collect, use, store, disclose, and protect your data in accordance with the New Zealand Privacy Act 2020 and its Information Privacy Principles (IPPs).

### 2. Information We Collect

We only collect personal information that is necessary for our lawful business functions. Depending on your interactions with us, we may collect:

* **Identity and Contact Data:** Name, email address, and account credentials.
* **User Content:** Ideas, votes, comments, prompts, and analysis documents you create or interact with.
* **Technical and Usage Data:** Authentication tokens (stored in browser local storage), IP addresses, browser types, device information, and interaction metrics.
* **Communications:** Records of correspondence, customer support inquiries, and feedback.

> **[BS note]:** Brainstormer does not collect billing addresses or payment details — remove any such categories before adoption. Extend "User Content" if deployments add file uploads, Slack mirroring, or social login (which would add provider profile data).

### 3. How We Collect Your Information

We collect personal information through the following methods:

* **Direct Collection:** Information you provide to us directly when creating an account, submitting ideas or prompts, voting, commenting, filling out forms, or communicating with our team.
* **Automated Collection:** Technical data collected automatically as you use the service, including authentication tokens kept in browser local storage and standard web telemetry.
* **Indirect Collection:** In limited circumstances, we may receive information about you from third parties (such as a configured Slack workspace or social login provider, where enabled). When we do, we take reasonable steps to ensure you are aware of this collection in compliance with IPP 3A.

### 4. Purpose and Use of Your Information

We collect and use your personal information solely for the following purposes:

* To provide accounts, generate and evaluate ideas, and manage your use of the service.
* To process AI requests: user-submitted prompts and idea content are sent to our configured AI provider for generation and analysis (see AI Processing note below).
* To communicate with you regarding your account, support requests, or changes to our policies.
* To improve our service functionality and user experience.
* To send marketing communications, provided you have explicitly opted in (you may opt out at any time).
* To comply with our legal and regulatory obligations.

> **[BS note — AI Processing disclosure, mandatory before adoption]:** Brainstormer sends user content (prompts, ideas, comments, supporting material) to a language model for idea generation and analysis. The policy must state which provider is configured (local Ollama vs hosted), what content is sent, retention at the provider, and any human review. The default local-Ollama posture (no external transmission) is a material fact worth stating explicitly.

### 5. Sharing and Disclosure of Information

We do not sell or rent your personal information. We will only disclose your data under the following circumstances:

* **Service Providers:** We may share data with trusted third parties (such as hosting, IT support, and — where the deployment enables them — Slack or social login providers) who require the information to perform services on our behalf.
* **Legal Requirements:** We may disclose your information if required or authorized by law, or to prevent or lessen a serious threat to public health or safety.
* **Business Transfers:** In the event of a merger, sale, or reorganization, customer information may be transferred as part of the business assets.

> **[BS note]:** With the default local-Ollama configuration, AI processing involves no external disclosure — say so explicitly, as it is a differentiator. Adopting hosted models or multi-tenant routing (see `Guide_MultiTenantAIConnectivity.md`) changes this section materially.

### 6. Cross-Border Data Transfers (Overseas Disclosure)

We utilize cloud-based services and third-party vendors that may store or process your data outside of New Zealand. In accordance with IPP 12, before we disclose your personal information to an overseas entity, we ensure that the recipient is subject to privacy laws that provide comparable safeguards to the New Zealand Privacy Act 2020, or we enter into binding contractual agreements (such as standard model clauses) to guarantee the protection of your data.

> **[BS note]:** With the default local-only deployment (local database, local Ollama, no external calls), cross-border disclosure may not occur at all — verify against the actual deployment and state the position explicitly. Enabling hosted AI providers re-activates this section.

### 7. Storage, Security, and Retention

We take all reasonable digital and physical security measures to protect your personal information against loss, unauthorized access, modification, or disclosure.

* **Security Safeguards:** We employ encryption, secure servers, and strict access controls to safeguard your data.
* **Data Retention:** We do not keep your personal information for longer than is necessary to achieve the lawful purpose for which it was collected. Once the data is no longer required, it is securely destroyed or permanently anonymized.

> **[BS note]:** Brainstormer's design retains history by default (soft-deleted ideas/comments, status-history and edit-audit trails). The adopted policy must reconcile this: define retention periods for each category, explain what "deletion" means in-app (e.g. discard/soft-delete vs hard erase), and provide a genuine erasure path for access/privacy requests.
* **Mandatory Breach Notification:** In the highly unlikely event of a privacy breach that we assess as likely to cause serious harm, we will promptly notify both you and the New Zealand Office of the Privacy Commissioner, as required by law.

### 8. Your Rights: Access and Correction

Under the Privacy Act 2020, you have the right to access the personal information we hold about you and request corrections if you believe it is inaccurate, incomplete, or out of date.

* **Access:** You may request a copy of your personal data at any time.
* **Correction:** If we agree the information is incorrect, we will update it. If we do not agree, you have the right to request that a statement of the correction sought be attached to your record.
* **Response Time:** We will acknowledge and respond to all access or correction requests as soon as reasonably practicable, and no later than 20 working days from receipt.

### 9. Privacy Complaints and Dispute Resolution

If you have concerns about how we have handled your personal information, or believe we have breached the Privacy Act 2020, please contact our Privacy Officer in the first instance. We investigate all complaints thoroughly and aim to resolve them quickly and respectfully.

If you are not satisfied with our response, you have the right to escalate your complaint to the New Zealand Office of the Privacy Commissioner (www.privacy.org.nz).

### 10. Contact Details

All privacy-related inquiries, access requests, or complaints should be directed to:

* **Privacy Officer:** [Name or Title]
* **Email:** [Privacy Email Address]
* **Phone:** [Phone Number]
* **Postal Address:** [Mailing Address]

---
