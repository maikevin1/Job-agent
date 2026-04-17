# Job Application Agent

## Overview

This project implements an agentic LLM-based web application designed to assist users in the job application process. The system allows users to store multiple resumes, input job descriptions, and automatically generate structured outputs including planning steps, extracted keywords, resume-job matching analysis, and a tailored cover letter.

Unlike a simple chatbot, this application uses a multi-step agent pipeline to decompose the task into several stages, making the system more structured, interpretable, and aligned with real-world workflows.

---

## Features

- Multi-step agent pipeline (planning, keyword extraction, matching, cover letter generation)
- Support for multiple resumes with persistent storage
- Job description and output history tracking
- Observability panel with detailed execution logs
- Metrics tracking including latency and success rate
- Fully deployed web application

---

## System Architecture

The system is built using a serverless architecture on AWS:

- Frontend: AWS Amplify Hosting
- API Layer: Amazon API Gateway
- Backend Logic: AWS Lambda
- Database: Amazon DynamoDB
- LLM Service: Amazon Bedrock

### Workflow

1. User interacts with the web interface (Amplify)
2. Requests are sent to API Gateway
3. API Gateway invokes Lambda functions
4. Lambda executes the agent pipeline
5. DynamoDB stores resumes and run history
6. Bedrock provides LLM inference
7. Results are returned to the frontend

---

## Agent Pipeline

The system implements a structured agent workflow with four steps:

1. Planning  
   Break down the job application task based on the job description.

2. Keyword Extraction  
   Extract key skills and requirements from the job description.

3. Resume Matching  
   Analyze how well the resume matches the job requirements.

4. Cover Letter Generation  
   Generate a tailored cover letter using both the resume and job description.

Each step is executed sequentially, and intermediate outputs are used to inform later stages.

---

## Observability

The system includes detailed observability to improve transparency and debugging:

- Agent execution steps
- Tool call logs with latency
- Total pipeline latency
- Success and failure tracking
- Error traces
- User interaction traces

All observability data is stored in DynamoDB and displayed in the frontend.

---

## Metrics

The system tracks two primary metrics:

- Latency  
  Measures the total execution time of the agent pipeline.

- Success Rate  
  Indicates whether a complete output (including a cover letter) is successfully generated.

These metrics are collected for each run and used to evaluate system performance.

---

## How to Use

1. Open the deployed web application
2. Enter and save a resume
3. Select a resume from the history panel
4. Input a job description
5. Click "Run Agent"
6. View outputs and observability logs

---

## Repository Structure

```
Job-agent/
├── index.html
├── lambda/
│   └── lambda_function.py
├── README.md
```

---

## Deployment

The application is deployed using AWS Amplify for frontend hosting. Backend services are implemented using API Gateway, Lambda, DynamoDB, and Amazon Bedrock.

---

## Limitations

- LLM outputs may contain inaccuracies or hallucinations
- Multiple model calls increase latency
- System incurs cost due to model usage
- No authentication or multi-user support in current version

---

## Future Work

- Reduce latency by optimizing pipeline steps
- Improve prompt design for better output quality
- Add user authentication and access control
- Implement caching to reduce repeated computation
- Extend to support additional job application features
