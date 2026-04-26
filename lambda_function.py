import json
import time
import os
import uuid
import traceback
from datetime import datetime
from decimal import Decimal
import boto3

region = "us-east-2"
model_id = os.environ.get("MODEL_ID")

bedrock = boto3.client("bedrock-runtime", region_name=region)
dynamodb = boto3.resource("dynamodb", region_name=region)

resume_table = dynamodb.Table("JobAgentResumes")
runs_table = dynamodb.Table("JobAgentRuns")


def decimal_converter(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def to_dynamodb_compatible(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [to_dynamodb_compatible(v) for v in value]
    if isinstance(value, dict):
        return {k: to_dynamodb_compatible(v) for k, v in value.items()}
    return value


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        },
        "body": json.dumps(body, default=decimal_converter)
    }


def call_llm(prompt, tool_name, observability):
    start = time.time()

    tool_record = {
        "tool_name": tool_name,
        "status": "started",
        "started_at": datetime.utcnow().isoformat()
    }
    observability["tool_calls"].append(tool_record)

    result = bedrock.converse(
        modelId=model_id,
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}]
            }
        ],
        inferenceConfig={
            "maxTokens": 700,
            "temperature": 0.2
        }
    )

    text = result["output"]["message"]["content"][0]["text"]
    duration = round(time.time() - start, 2)

    tool_record["status"] = "completed"
    tool_record["latency"] = duration
    tool_record["finished_at"] = datetime.utcnow().isoformat()

    return text


def safe_json_parse(text):
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end != -1:
            return json.loads(text[start:end])
        return json.loads(text)
    except Exception:
        return {
            "run_planning": True,
            "run_keyword_extraction": True,
            "run_resume_matching": True,
            "run_cover_letter": True,
            "reason": "Fallback decision: the model did not return valid JSON, so the system selected the full application workflow."
        }


def decide_workflow(jd, resume, observability):
    observability["agent_steps"].append("Step -1: Workflow decision started.")

    prompt = f"""
You are the workflow controller for a job application agent.

Given the resume and job description, decide which tools should be executed.

Available tools:
1. planning
2. keyword_extraction
3. resume_matching
4. cover_letter_generation

Return ONLY valid JSON in this exact format:
{{
  "run_planning": true,
  "run_keyword_extraction": true,
  "run_resume_matching": true,
  "run_cover_letter": true,
  "reason": "brief explanation"
}}

Decision rules:
- If both resume and job description are available, usually run the full workflow.
- If the job description is too short or unclear, still run keyword extraction but explain the limitation.
- If the resume is too short, still run matching but explain that the result may be limited.
- If the user appears to need application materials, run cover letter generation.
- You may skip a step only if it is clearly unnecessary.

Resume:
{resume}

Job Description:
{jd}
"""

    raw_decision = call_llm(prompt, "decide_workflow", observability)
    decision = safe_json_parse(raw_decision)

    decision = {
        "run_planning": bool(decision.get("run_planning", True)),
        "run_keyword_extraction": bool(decision.get("run_keyword_extraction", True)),
        "run_resume_matching": bool(decision.get("run_resume_matching", True)),
        "run_cover_letter": bool(decision.get("run_cover_letter", True)),
        "reason": decision.get("reason", "No reason provided.")
    }

    observability["workflow_decision"] = decision
    observability["agent_steps"].append(
        "Step -1: Workflow decision completed. "
        f"Decision={json.dumps(decision)}"
    )

    return decision


def plan_tasks(jd, observability):
    observability["agent_steps"].append("Step 0: Planning started.")
    result = call_llm(
        f"Break down the steps needed to apply for this job:\n{jd}",
        "plan_tasks",
        observability
    )
    observability["agent_steps"].append("Step 0: Planning completed.")
    return result


def extract_keywords(jd, observability):
    observability["agent_steps"].append("Step 1: Keyword extraction started.")
    result = call_llm(
        f"Extract key skills and requirements from this job description:\n{jd}",
        "extract_keywords",
        observability
    )
    observability["agent_steps"].append("Step 1: Keyword extraction completed.")
    return result


def match_resume(resume, keywords, observability):
    observability["agent_steps"].append("Step 2: Resume matching started.")
    result = call_llm(
        f"Given this resume:\n{resume}\n\n"
        f"And these job requirements:\n{keywords}\n\n"
        f"Analyze how well the resume matches the job.",
        "match_resume",
        observability
    )
    observability["agent_steps"].append("Step 2: Resume matching completed.")
    return result


def generate_cover_letter(jd, resume, observability):
    observability["agent_steps"].append("Step 3: Cover letter generation started.")
    result = call_llm(
        f"Write a professional cover letter based on this job description:\n{jd}\n\n"
        f"And this resume:\n{resume}",
        "generate_cover_letter",
        observability
    )
    observability["agent_steps"].append("Step 3: Cover letter generation completed.")
    return result


def agent_pipeline(jd, resume, resume_id):
    start = time.time()

    observability = {
        "agent_steps": [],
        "tool_calls": [],
        "workflow_decision": {},
        "error_trace": "",
        "success_path": [],
        "user_interaction_trace": [
            f"Resume selected: {resume_id}",
            "User submitted a new job description.",
            "Agent execution started."
        ]
    }

    try:
        decision = decide_workflow(jd, resume, observability)

        plan = ""
        keywords = ""
        match = ""
        cover_letter = ""

        if decision["run_planning"]:
            plan = plan_tasks(jd, observability)
        else:
            observability["agent_steps"].append("Step 0: Planning skipped by workflow decision.")

        if decision["run_keyword_extraction"]:
            keywords = extract_keywords(jd, observability)
        else:
            observability["agent_steps"].append("Step 1: Keyword extraction skipped by workflow decision.")

        if decision["run_resume_matching"]:
            if not keywords:
                keywords = "No extracted keywords available because keyword extraction was skipped."
            match = match_resume(resume, keywords, observability)
        else:
            observability["agent_steps"].append("Step 2: Resume matching skipped by workflow decision.")

        if decision["run_cover_letter"]:
            cover_letter = generate_cover_letter(jd, resume, observability)
        else:
            observability["agent_steps"].append("Step 3: Cover letter generation skipped by workflow decision.")

        latency = round(time.time() - start, 2)
        success = 1 if (plan or keywords or match or cover_letter) else 0

        observability["success_path"] = [
            "Resume retrieved successfully.",
            "LLM workflow decision completed.",
            "Selected tools executed according to workflow decision.",
            "Run saved successfully."
        ]
        observability["user_interaction_trace"].append("Agent execution completed successfully.")

        return {
            "plan": plan,
            "keywords": keywords,
            "match": match,
            "cover_letter": cover_letter,
            "latency": latency,
            "success": success,
            "workflow_decision": observability["workflow_decision"],
            "agent_steps": observability["agent_steps"],
            "tool_calls": observability["tool_calls"],
            "error_trace": observability["error_trace"],
            "success_path": observability["success_path"],
            "user_interaction_trace": observability["user_interaction_trace"]
        }

    except Exception:
        latency = round(time.time() - start, 2)
        error_trace = traceback.format_exc()

        observability["error_trace"] = error_trace
        observability["user_interaction_trace"].append("Agent execution failed.")
        observability["agent_steps"].append("Execution terminated due to error.")

        return {
            "plan": "",
            "keywords": "",
            "match": "",
            "cover_letter": "",
            "latency": latency,
            "success": 0,
            "workflow_decision": observability.get("workflow_decision", {}),
            "agent_steps": observability["agent_steps"],
            "tool_calls": observability["tool_calls"],
            "error_trace": observability["error_trace"],
            "success_path": observability["success_path"],
            "user_interaction_trace": observability["user_interaction_trace"]
        }


def save_resume(body):
    content = body.get("content", "").strip()
    title = body.get("title", "").strip()

    if not content:
        return response(400, {"error": "Resume content is required."})

    resume_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()

    if not title:
        title = content[:40].replace("\n", " ")

    item = {
        "resume_id": resume_id,
        "title": title,
        "content": content,
        "created_at": created_at
    }

    resume_table.put_item(Item=item)

    return response(200, {
        "message": "Resume saved successfully.",
        "resume": item
    })


def get_resumes():
    result = resume_table.scan()
    items = result.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return response(200, {"resumes": items})


def get_runs():
    result = runs_table.scan()
    items = result.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return response(200, {"runs": items})


def run_agent_and_save(body):
    jd = body.get("jd", "").strip()
    resume_id = body.get("resume_id", "").strip()

    if not jd:
        return response(400, {"error": "Job description is required."})

    if not resume_id:
        return response(400, {"error": "resume_id is required."})

    resume_result = resume_table.get_item(Key={"resume_id": resume_id})
    resume_item = resume_result.get("Item")

    if not resume_item:
        return response(404, {"error": "Resume not found."})

    resume_content = resume_item["content"]
    result = agent_pipeline(jd, resume_content, resume_id)

    run_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()

    run_item = {
        "run_id": run_id,
        "resume_id": resume_id,
        "resume_title": resume_item.get("title", ""),
        "job_description": jd,
        "plan": result["plan"],
        "keywords": result["keywords"],
        "match": result["match"],
        "cover_letter": result["cover_letter"],
        "latency": Decimal(str(result["latency"])),
        "success": result["success"],
        "workflow_decision": result["workflow_decision"],
        "agent_steps": result["agent_steps"],
        "tool_calls": result["tool_calls"],
        "error_trace": result["error_trace"],
        "success_path": result["success_path"],
        "user_interaction_trace": result["user_interaction_trace"],
        "created_at": created_at
    }

    run_item = to_dynamodb_compatible(run_item)
    runs_table.put_item(Item=run_item)

    result["run_id"] = run_id
    result["resume_id"] = resume_id
    result["resume_title"] = resume_item.get("title", "")
    result["created_at"] = created_at

    return response(200, result)


def delete_all_items(table, key_name):
    scan_response = table.scan()
    items = scan_response.get("Items", [])

    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={key_name: item[key_name]})

    while "LastEvaluatedKey" in scan_response:
        scan_response = table.scan(ExclusiveStartKey=scan_response["LastEvaluatedKey"])
        items = scan_response.get("Items", [])
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={key_name: item[key_name]})


def clear_history():
    delete_all_items(resume_table, "resume_id")
    delete_all_items(runs_table, "run_id")

    return response(200, {
        "message": "All resume history and job run history cleared successfully."
    })


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "")

    if method == "OPTIONS":
        return response(200, {"message": "CORS OK"})

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except Exception:
            return response(400, {"error": "Invalid JSON body."})

    if path == "/resume" and method == "POST":
        return save_resume(body)

    if path == "/resume" and method == "GET":
        return get_resumes()

    if path == "/runs" and method == "GET":
        return get_runs()

    if path == "/agent" and method == "POST":
        return run_agent_and_save(body)

    if path == "/clear-history" and method == "POST":
        return clear_history()

    return response(404, {"error": "Route not found."})
