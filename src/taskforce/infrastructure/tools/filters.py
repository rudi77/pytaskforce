import json
from typing import Any, Dict

def simplify_wiki_list_output(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduces the massive Azure DevOps Wiki JSON to just Name and ID.
    Drastically reduces token usage (from ~18k to ~500 tokens).
    """
    # Only filter if the tool call was successful
    if not result.get("success", False):
        return result

    raw_output = result.get("output", "")
    if not raw_output:
        return result

    try:
        # Handle case where output might be already a dict/list if not stringified
        if isinstance(raw_output, str):
            try:
                data = json.loads(raw_output)
            except json.JSONDecodeError:
                # If output isn't JSON string, leave it alone
                return result
        else:
            data = raw_output

        # Security check: Ensure it's a list as expected
        if isinstance(data, list):
            # THE FILTERING MAGIC: Keep only what matters
            lean_data = [
                {
                    "name": wiki.get("name"), 
                    "id": wiki.get("id"),
                    # Optional: "remoteUrl" if needed, but 'id' is key
                } 
                for wiki in data
                if isinstance(wiki, dict) # Safety check
            ]
            
            # Overwrite the output with the lean version
            # Always return string as output is expected to be string
            result["output"] = json.dumps(lean_data, indent=2)
            
    except Exception:
        # If anything goes wrong during filtering, return original result
        pass 

    return result

