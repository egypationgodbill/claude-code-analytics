"""
Report generation — inject metrics data into the HTML template.
"""

import json
import sys


def generate_report(data, output_path, template_path):
    """Generate the HTML report by injecting data into template."""
    try:
        with open(template_path, "r") as f:
            template = f.read()
    except IOError:
        print(f"Error: Template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    data_json = json.dumps(data, indent=None, default=str)
    html = template.replace("/*__REPORT_DATA__*/", f"window.__REPORT_DATA__ = {data_json};")

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Report generated: {output_path}")
    return output_path
