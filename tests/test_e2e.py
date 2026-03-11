import os
import json
import pytest
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables from .env BEFORE importing server
load_dotenv()

# Import the mcp instance and tools from server
import server

def get_text_from_mcp_result(result):
    """
    FastMCP.call_tool returns a tuple: (list_of_contents, extras_dict)
    This helper extracts the text from the first message in the list.
    """
    if isinstance(result, tuple) and len(result) > 0:
        contents = result[0]
        if isinstance(contents, list) and len(contents) > 0:
            content = contents[0]
            if hasattr(content, 'text'):
                return content.text
            return str(content)
    return str(result)

@pytest.mark.asyncio
async def test_e2e_flow_mcp():
    # 1. List children via MCP tool
    result = await server.mcp.call_tool("list_children", {})
    text = get_text_from_mcp_result(result)
    children_data = json.loads(text)
    
    if isinstance(children_data, dict) and "results" in children_data:
        children = children_data["results"]
    else:
        children = children_data

    assert len(children) > 0, "No children found in BabyBuddy instance"
    child_id = children[0]["id"]
    
    # 2. Add a note via MCP tool
    test_note_content = f"E2E Test Note (MCP) - {datetime.now(timezone.utc).isoformat()}"
    payload = {
        "child": child_id,
        "note": test_note_content,
        "time": datetime.now(timezone.utc).isoformat()
    }
    result = await server.mcp.call_tool("add_note", payload)
    text = get_text_from_mcp_result(result)
    created_note = json.loads(text)
    note_id = created_note["id"]
    assert created_note["note"] == test_note_content
    
    # 3. Verify the note exists via MCP tool
    # Using get_notes to find the note we just created
    result = await server.mcp.call_tool("get_notes", {"child": child_id})
    text = get_text_from_mcp_result(result)
    notes_data = json.loads(text)
    
    if isinstance(notes_data, dict) and "results" in notes_data:
        notes = notes_data["results"]
    else:
        notes = notes_data
        
    found = any(n["id"] == note_id for n in notes)
    assert found, f"Note {note_id} not found in notes list"
    
    # 4. Delete the note via MCP tool
    result = await server.mcp.call_tool("delete_note", {"note_id": note_id})
    text = get_text_from_mcp_result(result)
    delete_result = json.loads(text)
    assert delete_result["deleted"] is True
    
    # 5. Verify the note is gone
    result = await server.mcp.call_tool("get_notes", {"child": child_id})
    text = get_text_from_mcp_result(result)
    notes_data = json.loads(text)
    
    if isinstance(notes_data, dict) and "results" in notes_data:
        notes = notes_data["results"]
    else:
        notes = notes_data
        
    found = any(n["id"] == note_id for n in notes)
    assert not found, f"Note {note_id} still exists after deletion"
