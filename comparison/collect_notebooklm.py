"""Write NotebookLM's golden-set answers to data/comparison/notebooklm.jsonl.

Unlike the other two adapters, this isn't a live collector: NotebookLM has no
scriptable API (see docs/vs-managed-rag.md and the `compare-notebooklm`
Makefile target), so the 10 answers below were gathered by hand through the
NotebookLM web UI (a Google account, a notebook created manually, the three
corpus PDFs uploaded as native sources) on 2026-08-27. Question text and
ground_truth are reused from data/comparison/payments_rag.jsonl rather than
duplicated, since it's the same golden set.

Known fidelity gaps versus the other two systems, both logged so they aren't
mistaken for real numbers later:

  * `contexts` is set to the cited source filenames, not retrieved passage
    text: NotebookLM's UI only exposes which document a citation came from,
    not the passage itself. RAGAS's faithfulness/context_precision/
    context_recall need real passage text to mean anything, so those three
    scores are NOT comparable to payments-rag's or openai-file-search's for
    this system; `answer_relevancy` (question vs. answer, no context needed)
    still is.
  * `latency_s` is a rough constant from the human operator's observed
    10-20s-per-question range, not a per-question measurement.
  * Manual setup (account, notebook, PDF upload) took about 11 minutes,
    separate from and before the ~10-20s/question chat latency.

Run:

    PYTHONPATH=. python -m comparison.collect_notebooklm
"""

from __future__ import annotations

from pathlib import Path

from comparison.logging_setup import get_logger
from comparison.schema import SystemAnswer, append_jsonl, read_jsonl

GOLDEN_SOURCE = Path("data/comparison/payments_rag.jsonl")
OUT = Path("data/comparison/notebooklm.jsonl")

APPROX_LATENCY_S = 15.0  # midpoint of the observed 10-20s/question range

FIDELITY_NOTE = (
    "contexts are cited source filenames, not retrieved passage text; "
    "faithfulness/context_precision/context_recall are not meaningful for "
    "this system. latency_s is an approximate constant, not measured per "
    "question. Manual setup (account, notebook, PDF upload) took ~11 min."
)

ANSWERS: dict[str, dict] = {
    "sct-inst-max-execution-time": {
        "answer": "The target maximum execution time for an SCT Inst (SEPA Instant Credit Transfer) payment is 5 seconds. Specifically, latest at 5 seconds after the Originator PSP applies the electronic Time Stamp and sends the transaction, it must receive either a positive confirmation (stating that funds have been made available to the beneficiary) or a negative confirmation (a reject with an appropriate reason code). This target was reduced to 5 seconds (from 10 seconds) to align with the maximum timelines established by the amended SEPA Regulation. Additionally, participating Payment Service Providers (PSPs) are free to enter into bilateral or multilateral agreements to process transactions even faster, using a target maximum execution time of less than 5 seconds.",
        "citations": ["sct_inst_rulebook_2025.pdf"],
    },
    "sct-inst-availability": {
        "answer": "Yes, the SCT Inst scheme is fully available on weekends and public holidays. Transactions can be executed at any time of day, 24 hours a day, on all Calendar Days of the year (with \"Calendar Day\" defined under the scheme as any day of the year). To participate in the scheme, both Originator and Beneficiary Payment Service Providers (PSPs) are contractually obligated to maintain the capability to process transactions 24/7/365. This continuous availability is only subject to: the specific Payment Initiation Channel used to start the transfer, and short, foreseeable periods of planned maintenance or downtime, provided that these periods are kept short and users are informed about them in advance.",
        "citations": ["sample_sepa.pdf", "sct_inst_rulebook_2025.pdf"],
    },
    "sct-inst-timeout-no-confirmation": {
        "answer": "If the Originator PSP has received no confirmation message at all within 10 seconds of the Time Stamp, it must execute a specific set of procedures to protect the customer while maintaining the integrity of the transaction in the inter-PSP space:\n\n1. Immediate Actions for the Customer (Originator): Restore the Payment Account - the Originator PSP must immediately restore the Originator's Payment Account to the state it would have been in had the transaction not taken place, by lifting the Reservation of the Amount; and Inform the Customer - the Originator PSP must immediately and adequately inform the Originator about this status (concrete details/channels are left to the PSP).\n\n2. Mandatory Inter-PSP Space Obligations: Maintain Settlement Cover - even though the reservation is lifted on the customer's account, the Originator PSP must maintain the reserved funds on its account managed by its CSM and is contractually obliged to maintain settlement certainty for the Beneficiary PSP until an eventual confirmation message is received; No Unilateral Failure Assumption - the Originator PSP cannot assume the transaction has failed until it receives a formal confirmation reporting the failure.\n\n3. Permitted Next Steps for the Originator PSP: it may (a) start the optional status investigation procedure right after the 9th second of the Time Stamp (using dataset DS-07 to prompt an instant status check from the Beneficiary PSP and intermediate CSMs), (b) use alternative communication channels to gain clarity on the transaction, or (c) simply wait for the confirmation message to arrive.\n\n4. Handling Belated Confirmations (more than 10 seconds after the Time Stamp): if a negative confirmation is eventually received, the Originator PSP must immediately inform the Originator of the rejection; if a positive confirmation is eventually received, it must immediately inform the Originator of the belated successful execution - any further corrective action required for belatedly executed transactions falls outside the scope of the scheme.",
        "citations": ["sct_inst_rulebook_2025.pdf"],
    },
    "sct-inst-settlement-certainty": {
        "answer": "An SCT Inst transaction achieves upfront settlement certainty for the Beneficiary PSP through a pre-funded reservation mechanism managed by the Clearing and Settlement Mechanisms (CSMs): Originator PSP Authorization - when the Originator PSP prepares and sends the transaction message, it explicitly authorizes its CSM to reserve funds on its account to cover the transfer; Instant Fund Reservation - the Originator PSP's CSM instantly reserves these funds as settlement cover, and this ring-fencing of liquidity in the clearing layer establishes the \"upfront\" settlement certainty; The Transaction Message Implies Certainty - when the CSM of the Beneficiary PSP forwards the transaction message to the Beneficiary PSP, receipt of this message itself acts as the guarantee, meaning the Beneficiary PSP is assured of payment if it accepts the transaction for further processing; Safe Instant Release of Funds - because the scheme strictly obliges the Originator PSP to settle successfully completed transfers and provide this certainty, the Beneficiary PSP can safely and instantly make the funds available to the beneficiary, relying completely on the guarantee carried by that incoming transaction message.",
        "citations": ["sct_inst_rulebook_2025.pdf"],
    },
    "sct-inst-currency": {
        "answer": "SCT Inst payments are executed strictly in euro. This euro requirement applies to all stages of the transaction process, including all exception handling procedures such as Rejects, Recalls, and Requests for Recall by the Originator (RFRO). However, the Payment Accounts of the Originator and the Beneficiary do not have to be in euro - they can be denominated in euro or any other currency. If the accounts are in a different currency, the necessary currency conversion is performed directly by the Originator PSP or the Beneficiary PSP and is not governed by the SCT Inst scheme rules.",
        "citations": ["sct_inst_rulebook_2025.pdf"],
    },
    "sct-max-execution-time": {
        "answer": "The maximum execution time for a standard SCT (SEPA Credit Transfer) is one Banking Business Day following the point in time of receipt of the payment instruction. Under this standard timeline, the Originator PSP must credit the transfer amount to the Beneficiary PSP's account within this one-business-day limit; the Beneficiary PSP is then obliged to credit the beneficiary's account in accordance with the Payment Services Directive, meaning funds are made available to the beneficiary by the next business day at the latest. Key operational rules: Banking Business Days vs Calendar Days - unlike the 24/7/365 SCT Inst scheme, standard SCT transactions are calculated strictly using Banking Business Days, so if a payment obligation falls on a non-Banking-Business-Day, execution moves to the next Banking Business Day and the execution window is extended accordingly; Shorter Local Agreements - communities of participating PSPs may agree a shorter maximum execution time within their network; Cut-off Times - standard transfers are subject to cut-off times set by the Originator PSP, communicated to the originator, and outside the scope of the rulebook.",
        "citations": ["sct_rulebook_2025.pdf"],
    },
    "sct-charging-principle": {
        "answer": "In a standard SCT, charges are shared between the originator and the beneficiary using the \"Share\" (or \"SHA\") principle. This principle operates under the following rules: Separate Charging - the originator and the beneficiary are charged separately and individually by their respective providers (the Originator PSP and the Beneficiary PSP); Individual Responsibility - both the originator and the beneficiary are responsible solely for paying their own charges; Independent Pricing - the standard SCT scheme does not dictate the actual cost or tariff structure of these transfers, and the basis and level of charges are determined independently by each participating PSP in accordance with applicable law, making pricing entirely a transaction-level matter between the individual PSPs and their customers.",
        "citations": ["sct_rulebook_2025.pdf"],
    },
    "sct-remittance-length": {
        "answer": "In a standard SCT, the maximum length of remittance information depends on whether basic standard fields or the optional Extended Remittance Information (ERI) option is used. 1. Basic Remittance Information: under the standard logical datasets (attribute AT-T009), you can provide either Unstructured Remittance Information (maximum 140 characters) or Structured Remittance Information (maximum 140 characters). 2. Extended Remittance Information (ERI) Option: for PSPs who have adopted the optional ERI feature (Annex V of the Rulebook), a significantly larger volume of data can be transmitted for automated corporate reconciliation - Unstructured Portion (AT-T010): one occurrence of up to 140 characters; Structured Portion (AT-T011): up to 999 occurrences of structured data, each occurrence containing a maximum of 280 characters based on the ISO 20022 standard. Regardless of which option is used, all remittance data supplied by the originator must be forwarded in full and without alteration by the Originator PSP, any intermediaries, and the CSM to the Beneficiary PSP.",
        "citations": ["sct_rulebook_2025.pdf"],
    },
    "sct-recall-deadlines": {
        "answer": "Under both the standard SCT and the SCT Inst schemes, the deadlines for an Originator PSP to send a Recall request are identical and depend strictly on the reason for the recall. 1. Duplicate Sending & Technical Problems: deadline is within 10 Banking Business Days following the execution date of the initial transaction, applicable to the reasons \"Duplicate sending\" and \"Technical problems resulting in an erroneous SEPA Credit Transfer / SCT Inst\". 2. Fraud: deadline is within 13 months following the execution date of the initial transaction, applicable to the reason \"Fraudulent originated SEPA Credit Transfer / SCT Inst Instruction\". Regardless of the scheme, only one Recall can be sent per transaction. Furthermore, when the reason is a fraudulently originated transfer, the Originator PSP is allowed to include additional information in a comprehensible language to help the Beneficiary PSP investigate the request.",
        "citations": ["sct_rulebook_2025.pdf", "sct_inst_rulebook_2025.pdf"],
    },
    "sct-value-limits": {
        "answer": "No, the SCT schemes themselves do not set a maximum transaction limit at the business or regulatory level. While the SCT Instant (SCT Inst) scheme previously maintained a specific maximum transaction limit, this limit was officially removed; following amendments under the updated SEPA Regulation, there is no longer a maximum transaction amount stipulated at the scheme level for either standard SCT or SCT Inst. However, technical, bank-level, and clearing-level limits still apply: 1. Technical Message Limit - because both schemes rely on ISO 20022 XML standards, the message attribute containing the euro transfer amount (Attribute AT-T002) has a technical formatting limit: the euro portion must be larger than or equal to 0 and cannot exceed 999,999,999 euro, and the euro cents portion cannot exceed 99 cents, establishing an absolute technical transaction limit of 999,999,999.99 EUR per single transaction message. 2. Participant & Clearing Limits (CSM Limits) - settlement and value limits can still be applied outside the core scheme rules: CSMs or communities of participating PSPs can establish bilateral or multilateral settlement/value limits for risk management and liquidity control, and individual Originator PSPs are fully permitted to apply their own value limits to customer accounts and products based on their own risk appetite, risk management controls, and applicable law.",
        "citations": ["sct_inst_rulebook_2025.pdf", "sct_rulebook_2025.pdf"],
    },
}

log = get_logger("comparison.collect_notebooklm")


def run() -> None:
    golden = {r.question_id: r for r in read_jsonl(GOLDEN_SOURCE)}
    OUT.unlink(missing_ok=True)

    for question_id, data in ANSWERS.items():
        golden_row = golden[question_id]
        record = SystemAnswer(
            system="notebooklm",
            question_id=question_id,
            question=golden_row.question,
            answer=data["answer"],
            contexts=data["citations"],
            citations=data["citations"],
            ground_truth=golden_row.ground_truth,
            latency_s=APPROX_LATENCY_S,
            cost_usd=0.0,
            fidelity_note=FIDELITY_NOTE,
        )
        append_jsonl(OUT, record)
        log.info("notebooklm/%s: recorded (%d citation(s))", question_id, len(data["citations"]))

    log.info("wrote %d rows to %s", len(ANSWERS), OUT)


if __name__ == "__main__":
    run()
