import json
import os

def main():
    with open("audit_evidence.json", "r") as f:
        data = json.load(f)
        
    evidence_list = data["evidence"]
    db_rows = data.get("db_rows_after", {})
    
    md_content = "# FINAL QA EVIDENCE REPORT\n\n"
    
    # Write details for T01-T12
    for item in evidence_list:
        md_content += f"## {item['id']}: {item['query']}\n\n"
        
        md_content += "### 1. Original natural-language query\n"
        md_content += f"> {item['query']}\n\n"
        
        md_content += "### 2. Intent Agent output\n"
        md_content += "```json\n" + json.dumps(item.get('intent_output'), indent=2) + "\n```\n\n"
        
        md_content += "### 3. Retrieved schema tables\n"
        md_content += "```json\n" + json.dumps(item.get('schema_tables'), indent=2) + "\n```\n\n"
        
        md_content += "### 4. Generated SQL\n"
        md_content += "```sql\n" + str(item.get('sql_generated')) + "\n```\n\n"
        
        md_content += "### 5. Validation result\n"
        md_content += "```json\n" + json.dumps(item.get('validation_result'), indent=2) + "\n```\n\n"
        
        md_content += "### 6. Security result\n"
        md_content += "```json\n" + json.dumps(item.get('security_result'), indent=2) + "\n```\n\n"
        
        md_content += "### 7. Optimization result\n"
        md_content += "```json\n" + json.dumps(item.get('optimization_result'), indent=2) + "\n```\n\n"
        
        md_content += "### 8. Actual execution result\n"
        md_content += "```json\n" + json.dumps(item.get('execution_result'), indent=2) + "\n```\n\n"
        
        md_content += "### 9. Actual returned rows or row count\n"
        md_content += f"Row count: {item.get('row_count')}\n\n"
        
        md_content += "### 10. Explanation output\n"
        md_content += f"{item.get('explanation_output')}\n\n"
        
        md_content += "### 11. Retry count, if any\n"
        md_content += f"Retry count: {item.get('retry_count')}\n\n"
        
        md_content += "---\n\n"
        
    os.makedirs("docs", exist_ok=True)
    with open("docs/FINAL_QA_EVIDENCE.md", "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print("Report generated at docs/FINAL_QA_EVIDENCE.md")

if __name__ == "__main__":
    main()
