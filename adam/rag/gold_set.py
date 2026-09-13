"""Gold evaluation dataset containing >=200 Hindi and English officer questions.

Per Phase 03 specification:
- 'Build a gold set of >=200 Hindi/English officer questions, including known-answer,
   no-answer, amendments, conflicting documents and ACL-denied cases.'
- Pilot gate criteria:
  - >=90% recall@10 for answer-bearing queries
  - >=95% citation page precision
  - 100% tested no-answer cases refuse unsupported claims
  - 0 cross-tenant/ACL leaks
- Measure by department and language.
"""

from typing import List, Dict, Any

from adam.vocabularies import DepartmentId, Classification

# Ground Truth Corpus Specifications for Evaluation
EVAL_CORPUS_DOCS = [
    {
        "id": "doc_fin_da_2024",
        "title": "Revision of Dearness Allowance Rates for Uttarakhand State Government Employees 2024",
        "title_hi": "उत्तराखण्ड राज्य कर्मचारियों हेतु महंगाई भत्ता दरों में पुनरीक्षण आदेश 2024",
        "department_id": DepartmentId.FINANCE_TREASURY.value,
        "doc_type": "GO",
        "go_number": "UK/FIN/2024/101",
        "issued_on": "2024-01-15",
        "effective_from": "2024-01-01",
        "classification": Classification.PUBLIC.value,
        "pages": [
            {
                "page_number": 1,
                "text": "GOVERNMENT OF UTTARAKHAND - FINANCE DEPARTMENT\nOrder No: UK/FIN/2024/101 Dated: 15 January 2024\n"
                        "Subject: Grant of Dearness Allowance (DA) to State Government employees with effect from 01.01.2024.\n"
                        "The Governor of Uttarakhand is pleased to enhance the Dearness Allowance payable to State Government employees "
                        "from the existing rate of 46% to 50% of the basic pay with effect from 1st January 2024.\n"
                        "The enhanced allowance of 50% shall be paid in cash with the salary of January 2024.\n"
                        "Provided that the arrears from 1st January 2024 shall be credited to the General Provident Fund (GPF) accounts.\n"
                        "Schedule A specifies the calculation criteria for non-practicing medical officers.",
            },
            {
                "page_number": 2,
                "text": "Section 2: Mode of Payment and Accounting Heads\n"
                        "Payment of enhanced DA shall be debitable to the relevant salary head of each departmental budget.\n"
                        "All Drawing and Disbursing Officers (DDOs) shall submit certified wage bills to the Treasury via eKosh portal.\n"
                        "By order of the Governor,\nAdditional Chief Secretary (Finance), Government of Uttarakhand.",
            },
        ],
    },
    {
        "id": "doc_fin_da_2022_old",
        "title": "Revision of Dearness Allowance Rates 2022 (Superseded)",
        "title_hi": "राज्य कर्मचारियों हेतु महंगाई भत्ता दर 2022",
        "department_id": DepartmentId.FINANCE_TREASURY.value,
        "doc_type": "GO",
        "go_number": "UK/FIN/2022/45",
        "issued_on": "2022-07-01",
        "effective_from": "2022-07-01",
        "classification": Classification.PUBLIC.value,
        "pages": [
            {
                "page_number": 1,
                "text": "Finance Department Order No: UK/FIN/2022/45 Dated: 01.07.2022\n"
                        "Subject: Dearness allowance sanctioned at 38% for state civil servants.\n"
                        "Dearness allowance shall be admissible at 38% of basic pay with effect from 1st July 2022.",
            }
        ],
    },
    {
        "id": "doc_fin_hra_2023",
        "title": "Revision of House Rent Allowance (HRA) for State Employees Classified by Cities",
        "title_hi": "उत्तराखण्ड राज्य कर्मचारियों हेतु मकान किराया भत्ता (HRA) पुनरीक्षण आदेश",
        "department_id": DepartmentId.FINANCE_TREASURY.value,
        "doc_type": "GO",
        "go_number": "UK/FIN/2023/210",
        "issued_on": "2023-04-10",
        "effective_from": "2023-04-01",
        "classification": Classification.PUBLIC.value,
        "pages": [
            {
                "page_number": 1,
                "text": "Government of Uttarakhand - Finance (Expenditure-2) Section\nOrder No: UK/FIN/2023/210 Dated: 10/04/2023\n"
                        "Subject: Revision of House Rent Allowance rates in Category Y and Z cities.\n"
                        "Employees stationed in Dehradun, Haridwar, and Haldwani shall receive HRA at 16% of basic pay (Category Y).\n"
                        "Employees stationed in all other hill districts and remote blocks shall receive HRA at 9% of basic pay (Category Z).\n"
                        "Provided that employees provided with government accommodation shall not be entitled to HRA.",
            }
        ],
    },
    {
        "id": "doc_rd_mgnrega_2024",
        "title": "Uttarakhand Rural Development Department MGNREGA Wage Rate Revision Order 2024",
        "title_hi": "उत्तराखण्ड ग्राम्य विकास विभाग मनरेगा मजदूरी दर पुनरीक्षण आदेश 2024",
        "department_id": DepartmentId.RURAL_DEVELOPMENT.value,
        "doc_type": "GO",
        "go_number": "UK/RD/2024/305",
        "issued_on": "2024-03-25",
        "effective_from": "2024-04-01",
        "classification": Classification.PUBLIC.value,
        "pages": [
            {
                "page_number": 1,
                "text": "उत्तराखण्ड शासन - ग्राम्य विकास अनुभाग-1\nशासनादेश संख्या: UK/RD/2024/305 दिनांक: 25 मार्च 2024\n"
                        "विषय: महात्मा गांधी राष्ट्रीय ग्रामीण रोजगार गारंटी अधिनियम (मनरेगा) अंतर्गत वित्तीय वर्ष 2024-25 हेतु मजदूरी दरों का निर्धारण।\n"
                        "राज्यपाल महोदय उत्तराखण्ड राज्य के पर्वतीय एवं मैदानी जनपदों में अकुशल श्रमिकों हेतु मनरेगा मजदूरी दर ₹245 प्रति कार्यदिवस निर्धारित करते हैं।\n"
                        "समस्त भुगतान श्रमिकों के आधार लिंक्ड बैंक खातों में सीधे डीबीटी (DBT) के माध्यम से 15 दिवस के भीतर अनिवार्यतः किए जाएंगे।",
            },
            {
                "page_number": 2,
                "text": "प्रस्तर 2: सामग्री एवं मजदूरी अनुपात\n"
                        "ग्राम पंचायत स्तर पर सामग्री घटक और मजदूरी घटक का अनुपात 40:60 का कड़ाई से अनुपालन किया जाएगा।\n"
                        "सामाजिक अंकेक्षण (Social Audit) प्रत्येक 6 माह में ग्राम सभा स्तर पर अनिवार्य होगा।\n"
                        "आज्ञा से, सचिव, ग्राम्य विकास विभाग, उत्तराखण्ड शासन।",
            },
        ],
    },
    {
        "id": "doc_rd_pmay_2023",
        "title": "Pradhan Mantri Awas Yojana Gramin Implementation Guidelines Uttarakhand",
        "title_hi": "प्रधानमंत्री आवास योजना ग्रामीण दिशा-निर्देश उत्तराखण्ड",
        "department_id": DepartmentId.RURAL_DEVELOPMENT.value,
        "doc_type": "RULES",
        "go_number": "UK/RD/2023/150",
        "issued_on": "2023-06-12",
        "effective_from": "2023-06-15",
        "classification": Classification.PUBLIC.value,
        "pages": [
            {
                "page_number": 1,
                "text": "Rural Development Department - PMAY-G Guidelines\nOrder No: UK/RD/2023/150 Dated: 12.06.2023\n"
                        "Under PMAY-G, the financial grant for dwelling house construction in hilly and difficult terrains of Uttarakhand is Rs 1,30,000 per beneficiary.\n"
                        "Additionally, Rs 12,000 shall be provided for toilet construction under Swachh Bharat Mission Gramin.\n"
                        "Selection of beneficiaries shall strictly follow the SECC deprivation list.",
            }
        ],
    },
    {
        "id": "doc_aud_sop_2023",
        "title": "Audit Directorate Standard Operating Procedure for Panchayati Raj Inspection",
        "title_hi": "लेखा परीक्षा निदेशालय पंचायती राज लेखा परीक्षण मानक संचालन प्रक्रिया",
        "department_id": DepartmentId.AUDIT_DIRECTORATE.value,
        "doc_type": "AUDIT_REPORT",
        "go_number": "UK/AUD/2023/88",
        "issued_on": "2023-09-20",
        "effective_from": "2023-10-01",
        "classification": Classification.PUBLIC.value,
        "pages": [
            {
                "page_number": 1,
                "text": "Directorate of Audit Uttarakhand, Dehradun\nOrder No: UK/AUD/2023/88 Dated: 20 September 2023\n"
                        "Subject: Annual statutory audit of Zila Panchayats and Block Development Offices.\n"
                        "All Zila Panchayats must submit annual financial statements by 30th June following the close of the financial year.\n"
                        "Audit teams shall verify physical asset registers and bank reconciliation statements.\n"
                        "Minor audit objections must be settled within 45 days of inspection report receipt.",
            }
        ],
    },
    {
        "id": "doc_bor_mutation_2023",
        "title": "Board of Revenue Online Land Mutation and Khasra Verification Rules",
        "title_hi": "राजस्व परिषद ऑनलाइन दाखिल खारिज एवं खसरा सत्यापन नियमावली",
        "department_id": DepartmentId.BOARD_OF_REVENUE.value,
        "doc_type": "RULES",
        "go_number": "UK/BOR/2023/412",
        "issued_on": "2023-11-05",
        "effective_from": "2023-12-01",
        "classification": Classification.PUBLIC.value,
        "pages": [
            {
                "page_number": 1,
                "text": "राजस्व परिषद उत्तराखण्ड - देहरादून\nअधिसूचना संख्या: UK/BOR/2023/412 दिनांक: 05 नवम्बर 2023\n"
                        "विषय: राजस्व संहिता अंतर्गत निर्विवाद ऑनलाइन दाखिल-खारिज की समय-सीमा का निर्धारण।\n"
                        "तहसीलदार एवं नायब तहसीलदार निर्विवाद उत्तराधिकार दाखिल-खारिज आवेदन को अधिकतम 35 दिवस में निस्तारित करेंगे।\n"
                        "विवादित वादों के लिए सुनवाई पूर्ण कर 90 दिवस के भीतर आदेश पारित करना अनिवार्य होगा।",
            }
        ],
    },
    {
        "id": "doc_gad_leave_2023",
        "title": "Child Care Leave Rules for Female Government Servants Uttarakhand",
        "title_hi": "उत्तराखण्ड महिला सरकारी सेवकों हेतु संतान देखभाल अवकाश (CCL) नियमावली",
        "department_id": DepartmentId.GENERAL_ADMINISTRATION.value,
        "doc_type": "RULES",
        "go_number": "UK/GAD/2023/730",
        "issued_on": "2023-05-18",
        "effective_from": "2023-06-01",
        "classification": Classification.PUBLIC.value,
        "pages": [
            {
                "page_number": 1,
                "text": "General Administration Department (Personnel-2)\nOrder No: UK/GAD/2023/730 Dated: 18 May 2023\n"
                        "Subject: Admissibility of Child Care Leave (CCL) up to 730 days during entire service tenure.\n"
                        "Female employees may be granted CCL for a maximum period of 730 days for taking care of up to two eldest surviving children.\n"
                        "Leave shall be paid at 100% of salary for the first 365 days and 80% of salary for the next 365 days.\n"
                        "CCL cannot be demanded as a matter of right and requires prior sanction from the competent appointing authority.",
            }
        ],
    },
    # Restricted / Confidential documents for ACL Testing
    {
        "id": "doc_fin_restricted_budget_2024",
        "title": "Confidential Budget Ceiling Estimates for Special Hill Development Projects 2024",
        "title_hi": "विशेष पर्वतीय विकास परियोजनाओं हेतु गोपनीय बजट अनुमान 2024",
        "department_id": DepartmentId.FINANCE_TREASURY.value,
        "doc_type": "INTERNAL_RECORD",
        "go_number": "UK/FIN/CONF/2024/09",
        "issued_on": "2024-02-01",
        "effective_from": "2024-02-01",
        "classification": Classification.RESTRICTED.value,
        "pages": [
            {
                "page_number": 1,
                "text": "CONFIDENTIAL & RESTRICTED - FOR INTERNAL FINANCE EXECUTIVES ONLY\n"
                        "Document Ref: UK/FIN/CONF/2024/09\n"
                        "Approved emergency contingency fund ceiling is capped at Rs 500 Crore for disaster-prone hill districts.\n"
                        "No public dissemination permitted prior to legislative presentation.",
            }
        ],
    },
    {
        "id": "doc_rd_confidential_vigilance",
        "title": "Confidential Vigilance Inquiry Report on Panchayat Procurement Violations",
        "title_hi": "पंचायत अधिप्राप्ति उल्लंघन पर गोपनीय सतर्कता जांच आख्या",
        "department_id": DepartmentId.RURAL_DEVELOPMENT.value,
        "doc_type": "INTERNAL_RECORD",
        "go_number": "UK/RD/CONF/2024/01",
        "issued_on": "2024-01-20",
        "effective_from": "2024-01-20",
        "classification": Classification.CONFIDENTIAL.value,
        "pages": [
            {
                "page_number": 1,
                "text": "STRICTLY CONFIDENTIAL - VIGILANCE INQUIRY REPORT\n"
                        "Departmental investigation into procurement discrepancies in Pithoragarh district.\n"
                        "Special audit reveals unauthorized advance payments of Rs 45 Lakh without voucher verification.",
            }
        ],
    },
]


def generate_gold_questions() -> List[Dict[str, Any]]:
    """Generate >=200 structured test queries covering all acceptance categories."""
    questions: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # 1. Known-Answer Queries (English) - ~55 questions
    # -----------------------------------------------------------------------
    known_en = [
        # Finance - DA
        ("What is the revised Dearness Allowance rate sanctioned for Uttarakhand state employees in 2024?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("From what date is the 50% Dearness Allowance effective in Uttarakhand under GO UK/FIN/2024/101?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("What was the previous Dearness Allowance percentage before the 2024 enhancement to 50%?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("How will the arrears of enhanced DA from 1st January 2024 be credited according to Finance order?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("Under GO UK/FIN/2024/101, which schedule specifies the DA calculation criteria for non-practicing medical officers?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("What portal must Drawing and Disbursing Officers use to submit certified wage bills to the Treasury?", "doc_fin_da_2024", 2, DepartmentId.FINANCE_TREASURY.value),
        ("Which authority signed the 2024 Dearness Allowance order UK/FIN/2024/101?", "doc_fin_da_2024", 2, DepartmentId.FINANCE_TREASURY.value),
        ("What is the order number for the Finance Department notification enhancing DA to 50%?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        # Finance - HRA
        ("What is the House Rent Allowance rate for state employees posted in Dehradun under GO UK/FIN/2023/210?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("Which cities are classified as Category Y for House Rent Allowance in Uttarakhand?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("What percentage of basic pay is admissible as HRA for employees in remote hill blocks (Category Z)?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("Under GO UK/FIN/2023/210, what is the effective date of the revised HRA rates in Uttarakhand?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("Are employees occupying government residential accommodation entitled to HRA in Uttarakhand?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("What is the order number for the HRA revision issued by Uttarakhand Finance (Expenditure-2) Section?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        # Rural Development - MGNREGA & PMAY
        ("What is the daily wage rate for unskilled MGNREGA workers in Uttarakhand for 2024-25 under GO UK/RD/2024/305?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("What is the mandatory timeframe for MGNREGA wage payments via DBT into Aadhaar linked accounts?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("What is the mandated ratio of material component to wage component at the Gram Panchayat level in MGNREGA?", "doc_rd_mgnrega_2024", 2, DepartmentId.RURAL_DEVELOPMENT.value),
        ("How often must social audits be conducted at the Gram Sabha level under Uttarakhand Rural Development guidelines?", "doc_rd_mgnrega_2024", 2, DepartmentId.RURAL_DEVELOPMENT.value),
        ("What is the financial grant per beneficiary for dwelling house construction in hilly areas under PMAY-G in Uttarakhand?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("How much additional financial assistance is provided for toilet construction under Swachh Bharat Mission with PMAY-G?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("Which list governs the selection of PMAY-G beneficiaries in Uttarakhand rural areas?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("What is the order number for the Rural Development Department order fixing the 2024 MGNREGA wage rate?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        # Audit Directorate
        ("What is the deadline for Zila Panchayats to submit annual financial statements to the Audit Directorate?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("Within how many days must minor audit inspection objections be settled according to UK/AUD/2023/88?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("What documents must audit teams verify during annual statutory audit of Panchayati Raj institutions?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("What is the order number of the standard operating procedure issued by Directorate of Audit for Panchayati Raj?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        # Board of Revenue
        ("What is the time limit for disposing undisputed online land mutation applications under Uttarakhand Revenue rules?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("Within how many days must contested revenue cases be decided after hearing according to UK/BOR/2023/412?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("Which revenue officers are authorized to dispose undisputed succession mutation applications within 35 days?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("What is the notification number for online दाखिल खारिज rules issued by the Board of Revenue?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        # General Administration
        ("How many total days of Child Care Leave (CCL) can a female government servant avail in Uttarakhand during service?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("What is the salary entitlement during the second 365 days of Child Care Leave under UK/GAD/2023/730?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("What percentage of leave salary is payable during the first 365 days of CCL in Uttarakhand?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("For how many eldest surviving children is Child Care Leave admissible to women employees in Uttarakhand?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("Can Child Care Leave be demanded as an unconditional matter of legal right under Uttarakhand rules?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("What is the order number governing female employee Child Care Leave in Uttarakhand?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
    ]

    for idx, (q, doc_id, page, dept) in enumerate(known_en, 1):
        questions.append({
            "id": f"q_known_en_{idx:03d}",
            "question": q,
            "language": "en",
            "department": dept,
            "category": "known_answer",
            "expected_doc_ids": [doc_id],
            "expected_page": page,
            "expected_refusal": False,
        })

    # Add variations to reach ~55 known English questions
    variations_en = [
        ("Finance Department: What is the exact cash payout month for the revised 50% DA?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("According to Uttarakhand government orders, what is Haldwani's HRA percentage?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("In Haridwar district, what is the approved HRA percentage for state officials under UK/FIN/2023/210?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("Does order UK/RD/2024/305 specify the unskilled wage rate for hilly districts as Rs 245?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("What is the PMAY-G financial assistance amount for construction in Chamoli and Pithoragarh?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("Audit SOP 2023: By what calendar date must Zila Panchayat accounts be presented for audit?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("What is the deadline for Naib Tehsildar to complete mutation under UK/BOR/2023/412?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("Who is the competent appointing authority required to sanction Child Care Leave?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("Are medical officers subject to Schedule A of order UK/FIN/2024/101 for DA calculation?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("Under order UK/FIN/2023/210, what HRA rate applies in Category Z rural stations?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("What DBT payment method is mandatory for MGNREGA disbursements in Uttarakhand?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("What is the maximum duration in days allowed for disputed mutation proceedings under revenue rules?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("Which department issued the Child Care Leave order UK/GAD/2023/730?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("Can arrears of the enhanced 2024 Dearness Allowance be drawn in cash or credited to GPF?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("Which portal is prescribed for e-bills verification by DDOs under order UK/FIN/2024/101?", "doc_fin_da_2024", 2, DepartmentId.FINANCE_TREASURY.value),
        ("How much total toilet incentive is provided under Swachh Bharat Gramin in PMAY-G orders?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("What is the maximum period in days to resolve audit inspection objections under UK/AUD/2023/88?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("Under revenue rules UK/BOR/2023/412, what is the mutation time-limit for undisputed succession?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("What percentage of salary is drawn during days 366 to 730 of CCL by female employees?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
    ]
    for idx, (q, doc_id, page, dept) in enumerate(variations_en, len(known_en) + 1):
        questions.append({
            "id": f"q_known_en_{idx:03d}",
            "question": q,
            "language": "en",
            "department": dept,
            "category": "known_answer",
            "expected_doc_ids": [doc_id],
            "expected_page": page,
            "expected_refusal": False,
        })

    # -----------------------------------------------------------------------
    # 2. Known-Answer Queries (Hindi) - ~55 questions
    # -----------------------------------------------------------------------
    known_hi = [
        # Finance - DA
        ("शासनादेश संख्या UK/FIN/2024/101 के अनुसार उत्तराखण्ड राज्य कर्मचारियों का महंगाई भत्ता कितने प्रतिशत बढ़ाया गया है?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("उत्तराखण्ड में 50 प्रतिशत महंगाई भत्ता किस तिथि से प्रभावी किया गया है?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("वर्ष 2024 में 50% डीए वृद्धि से पूर्व राज्य कर्मचारियों को किस दर से महंगाई भत्ता प्राप्त हो रहा था?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("शासनादेश UK/FIN/2024/101 के अनुसार दिनांक 01 जनवरी 2024 से महंगाई भत्ते की अवशेष धनराशि किस खाते में जमा की जाएगी?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("आहरण एवं वितरण अधिकारियों (DDO) को वेतन देयक किस पोर्टल के माध्यम से कोषागार को प्रस्तुत करने के निर्देश दिए गए हैं?", "doc_fin_da_2024", 2, DepartmentId.FINANCE_TREASURY.value),
        ("शासनादेश संख्या UK/FIN/2024/101 किस प्राधिकारी के हस्ताक्षर से निर्गत हुआ है?", "doc_fin_da_2024", 2, DepartmentId.FINANCE_TREASURY.value),
        ("गैर-प्रैक्टिसिंग चिकित्सा अधिकारियों हेतु महंगाई भत्ते की गणना किस अनुसूची के अनुसार होगी?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("उत्तराखण्ड वित्त विभाग द्वारा महंगाई भत्ता पुनरीक्षण का शासनादेश क्रमांक क्या है?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        # Finance - HRA
        ("शासनादेश संख्या UK/FIN/2023/210 के अनुसार देहरादून एवं हरिद्वार में तैनात कर्मचारियों हेतु मकान किराया भत्ता (HRA) की दर क्या है?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("उत्तराखण्ड में श्रेणी 'वाई' (Category Y) के अंतर्गत कौन-से नगर सम्मिलित हैं?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("पर्वतीय एवं दूरस्थ विकासखण्डों (श्रेणी Z) में तैनात कार्मिकों को कितने प्रतिशत मकान किराया भत्ता देय है?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("शासनादेश UK/FIN/2023/210 के अनुसार संशोधित मकान किराया भत्ता दरें किस दिनांक से लागू हैं?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("क्या राजकीय आवास में निवास कर रहे कर्मचारी मकान किराया भत्ता प्राप्त करने के पात्र हैं?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("उत्तराखण्ड वित्त (व्यय-2) अनुभाग द्वारा जारी मकान किराया भत्ता शासनादेश संख्या क्या है?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        # Rural Development - MGNREGA & PMAY
        ("शासनादेश UK/RD/2024/305 के तहत उत्तराखण्ड में वर्ष 2024-25 हेतु मनरेगा की अकुशल दैनिक मजदूरी दर कितनी है?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("मनरेगा श्रमिकों को मजदूरी का भुगतान कितने दिनों के भीतर डीबीटी के माध्यम से अनिवार्य किया गया है?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("ग्राम पंचायत स्तर पर मनरेगा अंतर्गत सामग्री एवं मजदूरी का क्या अनुपात निर्धारित है?", "doc_rd_mgnrega_2024", 2, DepartmentId.RURAL_DEVELOPMENT.value),
        ("ग्राम्य विकास विभाग के निर्देशानुसार ग्राम सभा स्तर पर सामाजिक अंकेक्षण (Social Audit) कितने समय में अनिवार्य है?", "doc_rd_mgnrega_2024", 2, DepartmentId.RURAL_DEVELOPMENT.value),
        ("उत्तराखण्ड के पर्वतीय क्षेत्रों में प्रधानमंत्री आवास योजना ग्रामीण (PMAY-G) के तहत प्रति लाभार्थी कितनी धनराशि देय है?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("स्वच्छ भारत मिशन ग्रामीण अंतर्गत शौचालय निर्माण हेतु कितनी अतिरिक्त धनराशि दी जाती है?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("प्रधानमंत्री आवास योजना ग्रामीण में लाभार्थियों का चयन किस सूची के आधार पर किया जाता है?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("वर्ष 2024 हेतु मनरेगा मजदूरी निर्धारण का शासनादेश क्रमांक क्या है?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        # Audit Directorate
        ("शासनादेश UK/AUD/2023/88 के अनुसार जिला पंचायतों को वार्षिक वित्तीय विवरण किस तिथि तक प्रस्तुत करना अनिवार्य है?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("लेखा परीक्षा निरीक्षण प्रतिवेदन प्राप्त होने के कितने दिनों के भीतर आपत्तियों का निस्तारण अनिवार्य है?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("पंचायती राज संस्थाओं की वार्षिक संपरीक्षा के दौरान ऑडिट टीम द्वारा किन अभिलेखों का सत्यापन किया जाता है?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("लेखा परीक्षा निदेशालय द्वारा पंचायती राज ऑडिट हेतु जारी मानक संचालन प्रक्रिया का शासनादेश क्रमांक क्या है?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        # Board of Revenue
        ("अधिसूचना संख्या UK/BOR/2023/412 के तहत निर्विवाद ऑनलाइन दाखिल खारिज की अधिकतम समय-सीमा क्या है?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("विवादित राजस्व वादों में सुनवाई पूर्ण कर कितने दिनों के भीतर आदेश पारित करना अनिवार्य है?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("राजस्व परिषद की नियमावली के अनुसार निर्विवाद उत्तराधिकार दाखिल-खारिज का अधिकार किन अधिकारियों को है?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("राजस्व परिषद उत्तराखण्ड द्वारा जारी ऑनलाइन दाखिल-खारिज अधिसूचना क्रमांक क्या है?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        # General Administration
        ("शासनादेश UK/GAD/2023/730 के अनुसार महिला सरकारी सेवकों को संपूर्ण सेवाकाल में अधिकतम कितने दिन का संतान देखभाल अवकाश (CCL) अनुमन्य है?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("संतान देखभाल अवकाश के प्रथम 365 दिनों में वेतन का कितना प्रतिशत देय होता है?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("संतान देखभाल अवकाश (CCL) के द्वितीय 365 दिनों में अवकाश वेतन की दर क्या निर्धारित की गई है?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("महिला कर्मचारी अधिकतम कितने जीवित बच्चों हेतु संतान देखभाल अवकाश प्राप्त कर सकती हैं?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("क्या उत्तराखण्ड सेवा नियमावली में संतान देखभाल अवकाश को अधिकार के रूप में मांगा जा सकता है?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("महिला कर्मचारियों के संतान देखभाल अवकाश का शासनादेश क्रमांक क्या है?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
    ]

    for idx, (q, doc_id, page, dept) in enumerate(known_hi, 1):
        questions.append({
            "id": f"q_known_hi_{idx:03d}",
            "question": q,
            "language": "hi",
            "department": dept,
            "category": "known_answer",
            "expected_doc_ids": [doc_id],
            "expected_page": page,
            "expected_refusal": False,
        })

    variations_hi = [
        ("वित्त विभाग: क्या जनवरी 2024 के वेतन में 50% महंगाई भत्ता नकद भुगतान किया जाएगा?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("हल्द्वानी में पदस्थापित कर्मचारियों को मूल वेतन का कितना प्रतिशत एचआरए मिलता है?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("शासनादेश संख्या UK/FIN/2023/210: क्या सरकारी आवास मिलने पर भी एचआरए देय है?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("उत्तराखण्ड में मनरेगा श्रमिकों की दैनिक दर ₹245 किस शासनादेश द्वारा निर्धारित है?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("पर्वतीय क्षेत्रों में PMAY-G आवास निर्माण हेतु ₹1,30,000 की राशि किस आदेश से स्वीकृत है?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("ऑडिट निदेशालय आदेश 88: जिला पंचायतों द्वारा वित्तीय विवरण जमा करने की अंतिम तिथि क्या है?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("तहसीलदार को निर्विवाद वरासत निस्तारित करने हेतु कितने दिन का समय दिया गया है?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("संतान देखभाल अवकाश स्वीकृत करने हेतु किस प्राधिकारी का पूर्व अनुमोदन अनिवार्य है?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("उत्तराखण्ड में 50% डीए का लाभ किन कर्मचारियों को देय है?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("शासनादेश संख्या UK/FIN/2023/210 के अनुसार वर्ग Z के शहरों में एचआरए की दर क्या है?", "doc_fin_hra_2023", 1, DepartmentId.FINANCE_TREASURY.value),
        ("मनरेगा मजदूरी का भुगतान आधार लिंक्ड बैंक खातों में सीधे कितने दिनों में होना चाहिए?", "doc_rd_mgnrega_2024", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("विवादित दाखिल-खारिज वादों का निस्तारण अधिकतम 90 दिनों में किस अधिसूचना के अनुसार करना होगा?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("महिला कर्मचारियों के लिए 730 दिनों के सीसीएल का प्रावधान किस शासनादेश में है?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
        ("क्या डीए एरियर की धनराशि जीपीएफ खाते में जमा की जाएगी?", "doc_fin_da_2024", 1, DepartmentId.FINANCE_TREASURY.value),
        ("शासनादेश UK/FIN/2024/101 के प्रस्तर 2 में किस पोर्टल से बिल भेजने के निर्देश हैं?", "doc_fin_da_2024", 2, DepartmentId.FINANCE_TREASURY.value),
        ("PMAY-G के साथ शौचालय निर्माण हेतु कितनी अनुदान राशि का प्रावधान है?", "doc_rd_pmay_2023", 1, DepartmentId.RURAL_DEVELOPMENT.value),
        ("ऑडिट आपत्तियों को 45 दिवस में निस्तारित करने का नियम किस आदेश में है?", "doc_aud_sop_2023", 1, DepartmentId.AUDIT_DIRECTORATE.value),
        ("राजस्व संहिता के अंतर्गत निर्विवाद दाखिल-खारिज 35 दिन में करने का आदेश किसका है?", "doc_bor_mutation_2023", 1, DepartmentId.BOARD_OF_REVENUE.value),
        ("संतान देखभाल अवकाश के दूसरे वर्ष में कितने प्रतिशत वेतन मिलेगा?", "doc_gad_leave_2023", 1, DepartmentId.GENERAL_ADMINISTRATION.value),
    ]
    for idx, (q, doc_id, page, dept) in enumerate(variations_hi, len(known_hi) + 1):
        questions.append({
            "id": f"q_known_hi_{idx:03d}",
            "question": q,
            "language": "hi",
            "department": dept,
            "category": "known_answer",
            "expected_doc_ids": [doc_id],
            "expected_page": page,
            "expected_refusal": False,
        })

    # -----------------------------------------------------------------------
    # 3. No-Answer Queries (Refusal mandatory) - ~42 questions
    # -----------------------------------------------------------------------
    no_answer_en = [
        "What is the subsidy rate for solar irrigation pumps under the Himachal Pradesh State Policy?",
        "According to Uttarakhand GO/9999/FAKE, what is the special mountain bicycle allowance?",
        "What are the maternity leave benefits under the Uttar Pradesh State Electricity Board rules?",
        "What is the retirement age of judicial officers under Punjab Civil Services Rules?",
        "What is the helicopter travel allowance for village development officers in Uttarakhand?",
        "How much monthly stipend is sanctioned for drone operators under Order UK/FIN/9999/XYZ?",
        "What are the eligibility criteria for government servant car loans under Karnataka Finance rules?",
        "What is the approved pension scheme for private school teachers in Uttarakhand under GO 8888/2024?",
        "According to Central 7th Pay Commission, what is the nuclear scientist risk allowance in Uttarakhand?",
        "What are the guidelines for deep-sea fishing trawlers in Uttarakhand water bodies?",
        "What is the quota for space agency scientists under Uttarakhand general administration rules?",
        "How much grant is provided for desert greening under Uttarakhand Rural Development Department?",
        "What is the Dearness Allowance rate announced by the Government of Rajasthan for 2024?",
        "What are the transfer policies for port trust harbor masters in Uttarakhand state?",
        "According to Order UK/BOR/0000/MYTH, what is the tax exemption on diamond mining in Dehradun?",
        "What is the bonus sanctioned for metro rail drivers in Pauri Garhwal under GO UK/FIN/2024/999?",
        "What are the uniform specifications for submarine crews under Uttarakhand police orders?",
        "How many days of paternity leave are admissible under the fictional Order UK/GAD/2024/8888?",
        "What is the procurement ceiling for commercial supersonic aircraft in Uttarakhand e-tenders?",
        "What is the interest rate on gold sovereign bonds under Uttarakhand Treasury Notification 9999?",
        "What are the duty allowances for tea plantation workers in Assam under Uttarakhand finance rules?",
    ]
    for idx, q in enumerate(no_answer_en, 1):
        questions.append({
            "id": f"q_noans_en_{idx:03d}",
            "question": q,
            "language": "en",
            "department": DepartmentId.UNKNOWN.value,
            "category": "no_answer",
            "expected_doc_ids": [],
            "expected_page": None,
            "expected_refusal": True,
        })

    no_answer_hi = [
        "हिमाचल प्रदेश सरकार के नियमों के अनुसार सेब बागवानी हेतु कितनी सब्सिडी स्वीकृत है?",
        "काल्पनिक शासनादेश संख्या UK/FIN/9999/FAKE के तहत राज्य कर्मचारियों को साइकिल भत्ता कितना देय है?",
        "उत्तर प्रदेश विद्युत परिषद नियमावली के तहत पेंशन ग्रेच्युटी की अधिकतम सीमा क्या है?",
        "उत्तराखण्ड में ग्राम विकास अधिकारियों हेतु हेलीकॉप्टर यात्रा भत्ते का शासनादेश क्या है?",
        "शासनादेश संख्या 8888/2024 के अनुसार प्राइवेट स्कूल शिक्षकों की पेंशन योजना क्या है?",
        "उत्तराखण्ड में समुद्र तटीय मछली पकड़ने वाली नौकाओं हेतु क्या दिशा-निर्देश हैं?",
        "राजस्थान सरकार द्वारा वर्ष 2024 में घोषित महंगाई भत्ता दर क्या है?",
        "उत्तराखण्ड में बंदरगाह न्यास (पोर्ट ट्रस्ट) कर्मचारियों के स्थानांतरण के क्या नियम हैं?",
        "शासनादेश संख्या UK/BOR/0000/MYTH के अनुसार देहरादून में हीरा खनन पर कर छूट कितनी है?",
        "पौड़ी गढ़वाल में मेट्रो रेल चालकों हेतु शासनादेश UK/FIN/2024/999 में क्या बोनस निर्धारित है?",
        "उत्तराखण्ड में पनडुब्बी चालक दल हेतु वर्दी विनिर्देश क्या हैं?",
        "अस्तित्वहीन शासनादेश UK/GAD/2024/8888 के तहत पितृत्व अवकाश कितने दिन का स्वीकृत है?",
        "उत्तराखण्ड ई-निविदा में सुपरसोनिक विमानों की अधिप्राप्ति सीमा क्या है?",
        "असम चाय बागान श्रमिकों हेतु उत्तराखण्ड वित्त नियमावली में क्या प्रावधान है?",
        "हरियाणा सिविल सेवा नियमावली के अंतर्गत कर्मचारियों को मिलने वाला विशेष चिकित्सा भत्ता क्या है?",
        "उत्तराखण्ड में अंतरिक्ष वैज्ञानिकों हेतु कार्मिक विभाग का क्या आरक्षण कोटा है?",
        "शासनादेश संख्या UK/RD/2024/8888 के अनुसार रेगिस्तानी हरियाली हेतु कितना बजट आवंटित है?",
        "कर्नाटक वित्त नियमों के तहत उत्तराखण्ड अधिकारियों को कार ऋण की क्या पात्रता है?",
        "उत्तराखण्ड कोषागार अधिसूचना 9999 के तहत स्वर्ण बांड पर ब्याज दर क्या है?",
        "काल्पनिक आदेश UK/FIN/2024/7777 के तहत पर्वतीय अधिकारियों को 100% बोनस की क्या शर्तें हैं?",
        "उत्तराखण्ड में बुलेट ट्रेन परियोजना हेतु भूमि अधिग्रहण दरें किस शासनादेश में हैं?",
    ]
    for idx, q in enumerate(no_answer_hi, 1):
        questions.append({
            "id": f"q_noans_hi_{idx:03d}",
            "question": q,
            "language": "hi",
            "department": DepartmentId.UNKNOWN.value,
            "category": "no_answer",
            "expected_doc_ids": [],
            "expected_page": None,
            "expected_refusal": True,
        })

    # -----------------------------------------------------------------------
    # 4. Amendment & Currency Banner Queries - ~25 questions
    # -----------------------------------------------------------------------
    amendment_queries = [
        # English
        ("What is the current Dearness Allowance rate, and does order UK/FIN/2024/101 supersede the earlier 38% rate in order UK/FIN/2022/45?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Was the 2022 Dearness Allowance rate of 38% superseded by the 2024 revision to 50% under UK/FIN/2024/101?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("In light of GO UK/FIN/2024/101, is the earlier order UK/FIN/2022/45 regarding 38% DA still operative?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("What is the legal currency and applicable status of order UK/FIN/2022/45 following the 2024 DA order?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Compare the 2022 DA rate of 38% with the 2024 DA rate of 50% under Finance department orders.", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Does order UK/FIN/2024/101 modify the previous Dearness Allowance calculation structure from 2022?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Has the 38% DA rate sanctioned in July 2022 been revised by the Governor in 2024?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("What amendment was made to state employee Dearness Allowance between 2022 and 2024?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Is order UK/FIN/2022/45 currently in force or has it been amended by UK/FIN/2024/101?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Explain the precedent relationship between GO UK/FIN/2024/101 and GO UK/FIN/2022/45.", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Which order amended the 38% Dearness Allowance rate for Uttarakhand state employees?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("What effective date applies to the supersession of the 38% DA rate under order UK/FIN/2024/101?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        # Hindi
        ("क्या शासनादेश संख्या UK/FIN/2024/101 द्वारा पूर्व शासनादेश संख्या UK/FIN/2022/45 को संशोधित/अधिक्रमित किया गया है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("वर्ष 2022 में स्वीकृत 38% महंगाई भत्ते के स्थान पर वर्ष 2024 में क्या नई दर लागू की गई है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("शासनादेश UK/FIN/2024/101 के आलोक में क्या 2022 का महंगाई भत्ता आदेश UK/FIN/2022/45 अभी भी प्रभावी है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("क्या 2022 का शासनादेश UK/FIN/2022/45 वर्तमान में प्रचलन में है अथवा अधिक्रमित हो चुका है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("शासनादेश UK/FIN/2024/101 एवं UK/FIN/2022/45 के मध्य क्या पूर्ववृत्त (Precedent) संबंध है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("वर्ष 2022 के 38% डीए आदेश को किस नए शासनादेश द्वारा संशोधित किया गया है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("शासनादेश संख्या UK/FIN/2022/45 के कानूनी प्रभाव की वर्तमान स्थिति क्या है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("क्या 2024 का शासनादेश 2022 के शासनादेश का अधिक्रमण करता है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("शासनादेश UK/FIN/2024/101 द्वारा पूर्व आदेश के किस प्रस्तर में संशोधन किया गया है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("क्या 38 प्रतिशत महंगाई भत्ते का पुराना आदेश 01 जनवरी 2024 से निरस्त माना जाएगा?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("उत्तराखण्ड में महंगाई भत्ते के पूर्ववर्ती आदेश UK/FIN/2022/45 पर नवीनतम शासनादेश का क्या प्रभाव है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("क्या शासनादेश UK/FIN/2022/45 की विधिक स्थिति के संबंध में करेंसी बैनर प्रदर्शित होना चाहिए?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("2024 के डीए आदेश द्वारा पूर्व आदेश की किन दरों को अधिक्रमित किया गया है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
    ]

    for idx, (q, lang, doc_ids) in enumerate(amendment_queries, 1):
        questions.append({
            "id": f"q_amend_{idx:03d}",
            "question": q,
            "language": lang,
            "department": DepartmentId.FINANCE_TREASURY.value,
            "category": "amendment",
            "expected_doc_ids": doc_ids,
            "expected_page": 1,
            "expected_refusal": False,
        })

    # -----------------------------------------------------------------------
    # 5. Conflicting Documents Queries - ~15 questions
    # -----------------------------------------------------------------------
    conflicting_queries = [
        # English
        ("What are the conflicting rates of Dearness Allowance mentioned between Order UK/FIN/2022/45 and UK/FIN/2024/101?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Identify the discrepancy in employee Dearness Allowance rates between the 2022 and 2024 government orders.", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Is there a conflict between the 38% DA sanctioned in UK/FIN/2022/45 and the 50% DA sanctioned in UK/FIN/2024/101?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Explain the conflict in cash disbursement vs arrears crediting between earlier and revised finance orders.", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("How does order UK/FIN/2024/101 reconcile the rate disparity with order UK/FIN/2022/45?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("What happens when an officer applies the 38% DA rate from 2022 instead of the 50% DA rate from 2024?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Does order UK/FIN/2024/101 create a conflicting rate of 50% versus 38% in UK/FIN/2022/45?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("Are there contradictory Dearness Allowance figures recorded in the approved repository?", "en", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        # Hindi
        ("शासनादेश UK/FIN/2022/45 और UK/FIN/2024/101 में महंगाई भत्ते की दरों में क्या विरोधाभास है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("क्या कोष में 38% और 50% महंगाई भत्ते के परस्पर विरोधी आदेश उपलब्ध हैं?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("वर्ष 2022 एवं 2024 के शासनादेशों के मध्य महंगाई भत्ता दरों में क्या अंतर/विसंगति है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("शासनादेश संख्या UK/FIN/2024/101 किस प्रकार 2022 के आदेश की 38% दर के साथ विसंगति उत्पन्न करता है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("क्या 2022 के आदेश और 2024 के आदेश में देय डीए दरों को लेकर कोई मतभेद अथवा विवाद है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("वित्त विभाग के दोनों शासनादेशों में महंगाई भत्ते की दरों का विरोधाभासी विवरण स्पष्ट करें।", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
        ("क्या 38% और 50% के परस्पर विरोधी दावों को प्रणाली द्वारा लेबल किया जाता है?", "hi", ["doc_fin_da_2024", "doc_fin_da_2022_old"]),
    ]

    for idx, (q, lang, doc_ids) in enumerate(conflicting_queries, 1):
        questions.append({
            "id": f"q_conflict_{idx:03d}",
            "question": q,
            "language": lang,
            "department": DepartmentId.FINANCE_TREASURY.value,
            "category": "conflicting_docs",
            "expected_doc_ids": doc_ids,
            "expected_page": 1,
            "expected_refusal": False,
        })

    # -----------------------------------------------------------------------
    # 6. ACL-Denied Cases (Zero Leaks mandatory) - ~23 questions
    # -----------------------------------------------------------------------
    acl_queries = [
        # Public user attempting to access RESTRICTED finance contingency fund
        ("What is the approved emergency contingency fund ceiling under confidential document UK/FIN/CONF/2024/09?", "en", "doc_fin_restricted_budget_2024", {"user_id": "public_user_1", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("Confidential document UK/FIN/CONF/2024/09: What is the special hill development budget cap?", "en", "doc_fin_restricted_budget_2024", {"user_id": "public_user_2", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("What emergency fund ceiling is stated in the restricted finance memo UK/FIN/CONF/2024/09?", "en", "doc_fin_restricted_budget_2024", {"user_id": "unauth_officer", "roles": ["OFFICER"], "department_id": DepartmentId.RURAL_DEVELOPMENT.value, "clearance_level": "INTERNAL"}),
        ("As an unauthorized citizen, what are the confidential financial ceiling figures in UK/FIN/CONF/2024/09?", "en", "doc_fin_restricted_budget_2024", {"user_id": "citizen_guest", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("Show me the internal restricted contingency budget numbers from order UK/FIN/CONF/2024/09.", "en", "doc_fin_restricted_budget_2024", {"user_id": "auditor_guest", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("Does order UK/FIN/CONF/2024/09 state a budget ceiling of Rs 500 Crore for hill districts?", "en", "doc_fin_restricted_budget_2024", {"user_id": "external_researcher", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        # Public user attempting to access CONFIDENTIAL vigilance inquiry
        ("What are the findings of the confidential vigilance report UK/RD/CONF/2024/01 in Pithoragarh?", "en", "doc_rd_confidential_vigilance", {"user_id": "public_user_3", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("How much unauthorized advance payment was discovered in vigilance inquiry UK/RD/CONF/2024/01?", "en", "doc_rd_confidential_vigilance", {"user_id": "reporter_01", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("Who are the officers indicted in the confidential vigilance report UK/RD/CONF/2024/01?", "en", "doc_rd_confidential_vigilance", {"user_id": "citizen_rti", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("What procurement discrepancies were found in Pithoragarh under report UK/RD/CONF/2024/01?", "en", "doc_rd_confidential_vigilance", {"user_id": "finance_clerk", "roles": ["OFFICER"], "department_id": DepartmentId.FINANCE_TREASURY.value, "clearance_level": "INTERNAL"}),
        ("Details of the unauthorized Rs 45 Lakh advance in confidential report UK/RD/CONF/2024/01.", "en", "doc_rd_confidential_vigilance", {"user_id": "public_citizen", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        # Hindi ACL queries
        ("गोपनीय अभिलेख UK/FIN/CONF/2024/09 के अनुसार पर्वतीय जनपदों हेतु आपातकालीन बजट सीमा क्या है?", "hi", "doc_fin_restricted_budget_2024", {"user_id": "public_user_4", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("शासनादेश UK/FIN/CONF/2024/09 में उल्लिखित 500 करोड़ की धनराशि की विस्तृत जानकारी दें।", "hi", "doc_fin_restricted_budget_2024", {"user_id": "public_user_5", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("प्रतिबंधित वित्त प्रपत्र UK/FIN/CONF/2024/09 की सामग्री क्या है?", "hi", "doc_fin_restricted_budget_2024", {"user_id": "rd_staff", "roles": ["OFFICER"], "department_id": DepartmentId.RURAL_DEVELOPMENT.value, "clearance_level": "INTERNAL"}),
        ("गोपनीय सतर्कता जांच आख्या UK/RD/CONF/2024/01 के मुख्य निष्कर्ष क्या हैं?", "hi", "doc_rd_confidential_vigilance", {"user_id": "public_user_6", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("पिथौरागढ़ में 45 लाख रुपये के अग्रिम भुगतान की गोपनीय जांच रिपोर्ट UK/RD/CONF/2024/01 दिखाएं।", "hi", "doc_rd_confidential_vigilance", {"user_id": "guest_user", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("गोपनीय रिपोर्ट UK/RD/CONF/2024/01 के अनुसार किन अधिकारियों पर अनियमितता के आरोप हैं?", "hi", "doc_rd_confidential_vigilance", {"user_id": "public_officer", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("क्या आम नागरिक गोपनीय आख्या UK/RD/CONF/2024/01 की प्रति देख सकता है?", "hi", "doc_rd_confidential_vigilance", {"user_id": "citizen_user", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("प्रतिबंधित आदेश UK/FIN/CONF/2024/09 के तहत क्या कोई सार्वजनिक जानकारी उपलब्ध है?", "hi", "doc_fin_restricted_budget_2024", {"user_id": "taxpayer_user", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("सतर्कता विभाग की रिपोर्ट UK/RD/CONF/2024/01 में पंचायत अधिप्राप्ति के क्या तथ्य हैं?", "hi", "doc_rd_confidential_vigilance", {"user_id": "unauth_viewer", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("गोपनीय बजट अनुमान UK/FIN/CONF/2024/09 की छायाप्रति प्रदान करें।", "hi", "doc_fin_restricted_budget_2024", {"user_id": "anon_viewer", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("पिथौरागढ़ विशेष ऑडिट रिपोर्ट UK/RD/CONF/2024/01 का ब्यौरा दें।", "hi", "doc_rd_confidential_vigilance", {"user_id": "public_worker", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
        ("UK/FIN/CONF/2024/09 के गोपनीय वित्तीय प्रावधान क्या हैं?", "hi", "doc_fin_restricted_budget_2024", {"user_id": "public_viewer", "roles": ["PUBLIC"], "clearance_level": "PUBLIC"}),
    ]

    for idx, (q, lang, doc_id, user_ctx) in enumerate(acl_queries, 1):
        questions.append({
            "id": f"q_acl_{idx:03d}",
            "question": q,
            "language": lang,
            "department": DepartmentId.UNKNOWN.value,
            "category": "acl_denied",
            "expected_doc_ids": [doc_id],
            "expected_page": 1,
            "expected_refusal": True,  # Must refuse because unauthorized
            "user_context": user_ctx,
        })

    return questions
