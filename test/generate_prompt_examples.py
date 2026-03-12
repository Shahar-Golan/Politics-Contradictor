"""
Generate prompt examples for agent_info endpoint
"""
import sys
from pathlib import Path
import json

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from agent.react_agent import run_agent

# Test queries
queries = [
    "What does Donald Trump say about immigration policy?",
    "What is Barack Obama's opinion on healthcare reform?",
    "What does Elon Musk say about space exploration and life on Mars?"
]

def format_steps(result):
    """Format the agent steps for the API response"""
    steps = []
    for i, (thought, action, observation) in enumerate(zip(
        result['thoughts'],
        result['actions'],
        result['observations']
    ), 1):
        step = {
            "iteration": i,
            "module": action['tool'],
            "thought": thought,
            "action": {
                "tool": action['tool'],
                "parameters": action['parameters'],
                "reason": action.get('reason', '')
            },
            "observation": observation
        }
        steps.append(step)
    return steps

print("Generating prompt examples...\n")
print("="*80)

examples = []

for i, query in enumerate(queries, 1):
    print(f"\nExample {i}/{len(queries)}")
    print(f"Query: {query}")
    print("-"*80)
    
    # Run agent
    result = run_agent(query, max_iterations=5, verbose=True, use_llm=True)
    
    # Format example
    example = {
        "prompt": query,
        "full_response": result['final_answer'],
        "steps": format_steps(result),
        "metadata": {
            "iterations": result['iterations'],
            "tweets_found": result['tweets_found'],
            "urls_scraped": result['urls_scraped'],
            "mode": result['mode']
        }
    }
    examples.append(example)
    
    print("\n" + "="*80)

# Save to file
output_path = Path(__file__).parent / "prompt_examples.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(examples, f, indent=2, ensure_ascii=False)

print(f"\n✅ Examples saved to: {output_path}")
print(f"Generated {len(examples)} examples")
