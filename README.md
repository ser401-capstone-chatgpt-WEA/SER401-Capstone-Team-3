PBS Warn Data Normalizer
- This script takes raw emergency alert data from PBS Warn and converts it to a clean, GPT Readable JSON format

Requirements
- Python 3.8

Installation
- Donwload 'normalize_pbs_warn.py' and install it into a folder
- Move the desired files to be converted into the folder, named 'pbs_warn_raw.json' (this name can be changed by adjusting the script)
- Open command line within the folder, and run 'python normalize_pbs_warn.py'
- Open up the newly created 'pbs_warn_cleaned.json' for use as the final output

Example Input:
{
    "title": "Local Area Emergency",
    "message": "Franklin Co EM. Boil Water Advisory in effect for Louisburg customers. Repairs continue.",
    "sender": "201063,,Franklin County NC",
    "expires": "10/20/2025 07:25:00",
    "severity_color": "rgb(250, 58, 47)",
    "raw_html": "<div class=\"_3g3ZIcAdPcGK1KmFtttxbk\" style=\"background-color: rgb(250, 58, 47);\">Local Area Emergency <span role=\"img\" class=\"anticon _1blSVlicfjdRZLW-NqUpxi xJw27EU81B1Nrolkr8H8I\"><svg viewBox=\"0 0 512 512\" width=\"1em\" height=\"1em\" fill=\"currentColor\" aria-hidden=\"true\" focusable=\"false\" class=\"\"><path d=\"M504 256c0 136.967-111.033 248-248 248S8 392.967 8 256 119.033 8 256 8s248 111.033 248 248zM227.314 387.314l184-184c6.248-6.248 6.248-16.379 0-22.627l-22.627-22.627c-6.248-6.249-16.379-6.249-22.628 0L216 308.118l-70.059-70.059c-6.248-6.248-16.379-6.248-22.628 0l-22.627 22.627c-6.248 6.248-6.248 16.379 0 22.627l104 104c6.249 6.249 16.379 6.249 22.628.001z\"></path></svg></span></div><div class=\"LgcsbPsiL2uEI-nZqHF-e _4H2cZ9XlEm9L61-aIBF-c\">Franklin Co EM. Boil Water Advisory in effect for Louisburg customers. Repairs continue.</div><div class=\"ant-row\" style=\"row-gap: 0px;\"><div class=\"ant-col ant-col-xs-24 ant-col-lg-13\"><div class=\"_8JKc4-Z001p2NjobqPrgb\">SENDER</div><div class=\"_4H2cZ9XlEm9L61-aIBF-c KaOPUWJOTTTNW6GCsOo_v\">201063,,Franklin County NC</div></div><div class=\"ant-col ant-col-xs-0 ant-col-lg-1\"></div><div class=\"ant-col ant-col-xs-24 ant-col-lg-10\"><div class=\"_8JKc4-Z001p2NjobqPrgb\">EXPIRES</div><div class=\"_4H2cZ9XlEm9L61-aIBF-c\">10/20/2025 07:25:00</div></div></div>"
  }

Example output:
{
    "event_type": "Local Area Emergency",
    "status": "Active",
    "description": "Franklin Co EM. Boil Water Advisory in effect for Louisburg customers. Repairs continue.",
    "sender": "201063  Franklin County NC",
    "severity": "Severe",
    "issued": "2025-10-20T07:25:00Z",
    "expires": "2025-10-20T07:25:00Z"
  }

As shown above, this script successfully pulls the important information from inputted alerts, while cleaning up the detailed raw info that would be wasted inefficiency or confusion if given to chatGPT

This script automatically cleans up sender names, detects current advisory status, converts colors to severity levels, and converts times to ISO-8601 UTC format
