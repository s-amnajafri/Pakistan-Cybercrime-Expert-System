# Pakistan Cybercrime Complaint Assessment & Reporting Expert System

A rule-based expert system developed using Python and Streamlit to help individuals understand and respond to suspected cybercrime incidents in Pakistan.

The system evaluates user-provided information and generates an incident classification, assesses urgency, recommends appropriate actions, and provides relevant reporting resources and evidence-preservation guidance.

It uses **forward chaining** to reason through a knowledge base of IF-THEN rules and produce explainable results.

This project is developed as part of the **Introduction to Artificial Intelligence (IAI)** course.

## Project Objectives

- Identify and classify suspected cybercrime incidents based on user responses.
- Determine incident urgency and recommend appropriate actions.
- Provide decision-support information, including reporting channels, evidence checklists and safety precautions.
- Demonstrate rule-based reasoning through forward chaining.
- Explain the conclusions reached by displaying activated rules, supporting facts and inference stages.

## Expert System Components

The application implements four major components:

1. **Diagnosis:** Identifies the suspected cybercrime category using predefined rules.
2. **Decision Making:** Determines incident urgency and generates a prioritized action plan.
3. **Decision Support:** Provides reporting guidance, evidence-preservation advice and protective recommendations.
4. **Inference:** Uses forward chaining to derive facts and reach conclusions through a sequence of rule activations.

## Project Structure

| File / Folder | Description |
|---|---|
| `app.py` | Streamlit user interface and questionnaire |
| `engine.py` | Inference engine, forward chaining, explanations and what-if analysis |
| `rules.py` | Knowledge base containing questions, facts and IF-THEN rules |
| `test_scenarios.py` | Test scenarios, structural checks and randomized testing |
| `.streamlit/config.toml` | Streamlit theme and application settings |
| `requirements.txt` | Python dependencies |

## Technologies Used

- Python
- Streamlit
- Rule-based Expert Systems
- Forward Chaining
- IF-THEN Production Rules

## Installation and Local Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/YOUR_USERNAME/Pakistan-Cybercrime-Expert-System.git
   ```

2. Navigate to the project directory:

   ```bash
   cd Pakistan-Cybercrime-Expert-System
   ```

3. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:

   ```bash
   streamlit run app.py
   ```

## Running the Tests

Execute the test suite using:

```bash
python test_scenarios.py
```

The tests cover predefined incident scenarios, structural checks and randomized user-answer combinations.

## Deployment

The application can be deployed using Streamlit Community Cloud.

1. Push the project files to a GitHub repository.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) using GitHub.
3. Select the project repository and the `main` branch.
4. Set the main file path to `app.py`.
5. Deploy the application and access it through the generated public URL.

## Limitations and Disclaimer

- The system provides guidance and preliminary incident classification, not an official legal determination.
- It does not investigate offenders, file complaints or guarantee financial recovery.
- Reporting recommendations are informational and should be verified against the relevant official authorities.
- The application does not intentionally store or transmit questionnaire answers. However, the hosting platform may retain technical logs.
- Users should never enter passwords, OTPs, PINs or sensitive identification numbers.

## Reporting Information

Reporting guidance references relevant Pakistani authorities and institutions, including:

- National Cyber Crime Investigation Agency (NCCIA)
- State Bank of Pakistan (SBP)
- Pakistan Telecommunication Authority (PTA)
- Pakistan Computer Emergency Response Team (PKCERT)

Users should verify current reporting procedures and contact details through official websites.
