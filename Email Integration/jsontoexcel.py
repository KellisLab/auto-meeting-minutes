import pandas as pd
import re
from typing import List, Dict, Any

def parse_meeting_analysis(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse the meeting analysis text file and extract structured data
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Split content by topic sections
    topic_sections = re.split(r'## 🎯 "', content)[1:]  # Skip the header section
    
    parsed_data = []
    
    for section in topic_sections:
        # Extract topic title
        topic_match = re.search(r'^([^"]*)"', section)
        topic = topic_match.group(1) if topic_match else "Unknown"
        
        # Extract context
        context_match = re.search(r'\*\*Context:\*\* "([^"]*)"', section)
        context = context_match.group(1) if context_match else "No context found"
        
        # Extract description
        description_match = re.search(r'\*\*Description:\*\* ([^\n]*)', section)
        description = description_match.group(1) if description_match else "No description found"
        
        # Extract related concepts
        concepts_match = re.search(r'\*\*Related Concepts:\*\* ([^\n]*)', section)
        related_concepts = concepts_match.group(1) if concepts_match else "No concepts found"
        
        # Extract code matches count
        matches_count_match = re.search(r'\*\*Code Matches Found:\*\* (\d+)', section)
        code_matches_found = int(matches_count_match.group(1)) if matches_count_match else 0
        
        # Extract code match details
        code_sections = re.split(r'### \d+\. ', section)[1:]  # Skip the main section
        
        if code_sections:
            for code_section in code_sections:
                # Extract function name and score
                func_match = re.search(r'`([^`]+)`\s*\(Score:\s*([\d.]+)\)', code_section)
                function_name = func_match.group(1) if func_match else "Unknown function"
                score = func_match.group(2) if func_match else "0"
                
                # Extract file path
                file_match = re.search(r'\*\*File:\*\* `([^`]+)`', code_section)
                file_path = file_match.group(1) if file_match else "Unknown file"
                
                # Extract lines
                lines_match = re.search(r'\*\*Lines:\*\* ([^\n]*)', code_section)
                lines = lines_match.group(1) if lines_match else "Unknown"
                
                # Extract reasoning
                reasoning_match = re.search(r'\*\*Reasoning:\*\* ([^\n]*)', code_section)
                reasoning = reasoning_match.group(1) if reasoning_match else "No reasoning found"
                
                # Extract code preview
                code_match = re.search(r'```python\n(.*?)\n```', code_section, re.DOTALL)
                code_preview = code_match.group(1) if code_match else "No code preview"
                
                parsed_data.append({
                    'Topic': topic,
                    'Context': context,
                    'Description': description,
                    'Related Concepts': related_concepts,
                    'Code Matches Found': code_matches_found,
                    'Function Name': function_name,
                    'Score': score,
                    'File': file_path,
                    'Lines': lines,
                    'Reasoning': reasoning,
                    'Code Preview': code_preview
                })
        else:
            # If no code sections found, still add the topic info
            parsed_data.append({
                'Topic': topic,
                'Context': context,
                'Description': description,
                'Related Concepts': related_concepts,
                'Code Matches Found': code_matches_found,
                'Function Name': '',
                'Score': '',
                'File': '',
                'Lines': '',
                'Reasoning': '',
                'Code Preview': ''
            })
    
    return parsed_data

def create_excel_report(data: List[Dict[str, Any]], output_file: str):
    """
    Create an Excel file with the parsed data
    """
    df = pd.DataFrame(data)
    
    # Reorder columns as requested
    column_order = [
        'Topic', 'Context', 'Description', 'Related Concepts', 
        'Code Matches Found', 'Function Name', 'Score', 'File', 
        'Lines', 'Reasoning', 'Code Preview'
    ]
    
    df = df[column_order]
    
    # Create Excel writer with formatting
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Meeting Analysis', index=False)
        
        # Get the worksheet to apply formatting
        worksheet = writer.sheets['Meeting Analysis']
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            # Set a reasonable maximum width
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Make header row bold
        for cell in worksheet[1]:
            cell.font = cell.font.copy(bold=True)
    
    print(f"Excel file created successfully: {output_file}")
    print(f"Total records: {len(df)}")

def main():
    """
    Main function to convert meeting analysis to Excel
    """
    # Input and output file paths
    input_file = "filename.md"
    output_file = "meeting_analysis.xlsx"  # Change this to your desired output path
    
    try:
        # Parse the meeting analysis file
        print("Parsing meeting analysis file...")
        parsed_data = parse_meeting_analysis(input_file)
        
        if not parsed_data:
            print("No data found in the input file.")
            return
        
        # Create Excel report
        print("Creating Excel report...")
        create_excel_report(parsed_data, output_file)
        
        # Display summary
        print(f"\nSummary:")
        print(f"- Topics processed: {len(set(item['Topic'] for item in parsed_data))}")
        print(f"- Total code matches: {len([item for item in parsed_data if item['Function Name']])}")
        
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        print("Please make sure the file exists and update the file path in the script.")
    except Exception as e:
        print(f"Error processing file: {str(e)}")

if __name__ == "__main__":
    # Required packages - install with: pip install pandas openpyxl
    try:
        import pandas as pd
        import openpyxl
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("Please install required packages with:")
        print("pip install pandas openpyxl")
        exit(1)
    
    main()
