#!/home/wikibot/pywikibot-env/bin/python3.9
import requests
import re
import time
import json
import urllib.parse
import sys
import os
import warnings
import argparse
import subprocess

# Parse command line arguments
parser = argparse.ArgumentParser(description='iNaturalist reference bot for wiki pages')
parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without making actual edits')
parser.add_argument('--debug', action='store_true', help='Show detailed debugging output')
args = parser.parse_args()

# Set up logging based on debug flag
def log_debug(message):
    if args.debug:
        print(message)

def log_info(message):
    print(message)

if args.dry_run:
    log_info("Running in DRY RUN mode - no actual changes will be made to the wiki")

# Configuration
WIKI_API_URL = "https://mycomap.org/wiki/api.php"
WIKI_INDEX_URL = "https://mycomap.org/wiki/index.php"
INATURALIST_BASE_URL = "https://www.inaturalist.org/observations"
CHECK_INTERVAL = 3600  # Check every hour (in seconds)
USERNAME = "Taxonomybot"  # Replace with your wiki bot username
PASSWORD_FILE = ".wikibotpassword"  # File containing the password
VERIFY_SSL = False  # Verify SSL not needed because we are running this locally, and OpenSSL version conflicts make using this difficult
API_RATE_LIMIT = 1.0  # Minimum seconds between API requests to iNaturalist
MYCOMAP_URL_SCRIPT = "/home/wikibot/bin/get.mycomapurl.py"  # Path to the script for getting MycoMap URLs

# Read password from file
def read_password():
    try:
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Construct the path to the password file
        password_path = os.path.join(script_dir, PASSWORD_FILE)

        # Read the password from the file
        with open(password_path, 'r') as file:
            password = file.read().strip()

        if not password:
            log_info(f"Error: Password file {PASSWORD_FILE} is empty")
            sys.exit(1)

        return password
    except FileNotFoundError:
        log_info(f"Error: Password file {PASSWORD_FILE} not found")
        sys.exit(1)
    except Exception as e:
        log_info(f"Error reading password file: {e}")
        sys.exit(1)

# Timestamp of last API request to iNaturalist
last_api_request_time = 0

# Suppress insecure request warnings if not verifying SSL
if not VERIFY_SSL:
    warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# Helper function to make rate-limited API requests
def rate_limited_request(url, params=None, method="get"):
    global last_api_request_time

    # Check if we need to wait to respect the rate limit
    time_since_last_request = time.time() - last_api_request_time
    if time_since_last_request < API_RATE_LIMIT:
        # Calculate how long we need to wait
        wait_time = API_RATE_LIMIT - time_since_last_request
        # log_debug(f"Rate limiting: Waiting {wait_time:.2f} seconds before making API request")
        time.sleep(wait_time)

    # Make the request
    if method.lower() == "get":
        response = requests.get(url, params=params)
    else:
        response = requests.post(url, data=params)

    # Update the timestamp
    last_api_request_time = time.time()

    return response

# Login to wiki
def wiki_login():
    session = requests.Session()

    # Get the password from the file
    password = read_password()

    # Get login token
    params = {
        "action": "query",
        "meta": "tokens",
        "type": "login",
        "format": "json"
    }
    response = session.get(url=WIKI_API_URL, params=params, verify=VERIFY_SSL)
    data = response.json()
    if "query" not in data or "tokens" not in data["query"]:
        log_debug(f"Failed to get login token: {data}")
        return None

    login_token = data["query"]["tokens"]["logintoken"]

    # Login
    params = {
        "action": "login",
        "lgname": USERNAME,
        "lgpassword": password,
        "lgtoken": login_token,
        "format": "json"
    }
    response = session.post(WIKI_API_URL, data=params, verify=VERIFY_SSL)

    if response.json().get("login", {}).get("result") != "Success":
        log_debug(f"Login failed: {response.json()}")
        return None

    log_debug(f"Successfully logged in as {USERNAME}")
    return session

# Get recent changes - focus on new pages
def get_new_pages(session, rcstart=None):
    params = {
        "action": "query",
        "list": "recentchanges",
        "rctype": "new",
        "rcnamespace": "0",  # Main namespace
        "rclimit": "50",
        "format": "json"
    }
    if rcstart:
        params["rcstart"] = rcstart

    response = session.get(url=WIKI_API_URL, params=params, verify=VERIFY_SSL)
    data = response.json()
    if "query" not in data or "recentchanges" not in data["query"]:
        log_debug(f"Failed to get recent changes: {data}")
        return []

    return data["query"]["recentchanges"]

# Get page content
def get_page_content(session, title):
    params = {
        "action": "parse",
        "page": title,
        "prop": "wikitext",
        "format": "json"
    }
    response = session.get(url=WIKI_API_URL, params=params, verify=VERIFY_SSL)
    data = response.json()

    if "parse" not in data or "wikitext" not in data["parse"]:
        log_debug(f"Failed to get page content for {title}: {data}")
        return None

    return data["parse"]["wikitext"]["*"]

# Extract species name from page title
def extract_species_name(page_title):
    # Replace underscores with spaces
    species_name = page_title.replace("_", " ")

    # Handle URL encoded characters
    species_name = urllib.parse.unquote(species_name)

    return species_name

# Get MycoMap URL for a species
def get_mycomap_url(species_name):
    try:
        # Call the external script to get the URL
        log_debug(f"Getting MycoMap URL for: {species_name}")
        result = subprocess.run([MYCOMAP_URL_SCRIPT, species_name],
                               capture_output=True, text=True, check=True)
        url = result.stdout.strip()

        # Validate that we got a proper URL
        if url and url.startswith("https://mycomap.com/taxonomy/"):
            log_debug(f"Found MycoMap URL: {url}")
            return url
        else:
            log_debug(f"Invalid or empty MycoMap URL returned: {url}")
            return None
    except subprocess.CalledProcessError as e:
        log_debug(f"Error getting MycoMap URL: {e}")
        log_debug(f"Script output: {e.stdout}")
        log_debug(f"Script error: {e.stderr}")
        return None
    except Exception as e:
        log_debug(f"Unexpected error getting MycoMap URL: {e}")
        return None

# Check if iNaturalist has observations with this name
def check_inaturalist(species_name):
    found_in_main_taxonomy = False
    found_in_provisional = False

    try:
        # STEP 1: Check in main taxonomy using two possible approaches
        log_debug(f"\nCHECKING MAIN TAXONOMY: Checking iNaturalist for species: {species_name}")
        encoded_name = urllib.parse.quote(species_name)

        # First approach: Check if the taxon exists in the formal taxonomy database
        taxon_url = f"https://api.inaturalist.org/v1/taxa?q={encoded_name}"
        log_debug(f"Querying iNaturalist taxon API: {taxon_url}")

        response = rate_limited_request(taxon_url)
        if response.status_code == 200:
            data = response.json()

            # Check if we found any matching taxa
            if data and 'results' in data and len(data['results']) > 0:
                # Filter for exact name match or accepted name
                matching_taxa = [t for t in data['results']
                               if t.get('name') == species_name or
                                  t.get('preferred_common_name') == species_name or
                                  any(n.get('name') == species_name for n in t.get('taxon_names', []))]

                if matching_taxa:
                    log_debug(f"SUCCESS: Found matching taxon in main taxonomy for: {species_name}")
                    found_in_main_taxonomy = True
                else:
                    log_debug(f"No exact match found in main taxonomy database for: {species_name}")
            else:
                log_debug(f"No taxa found in main taxonomy database matching: {species_name}")
        else:
            log_debug(f"iNaturalist taxa API returned status code {response.status_code}")

        # Second approach (if first fails): Check for observations with this taxon name
        if not found_in_main_taxonomy:
            api_url = "https://api.inaturalist.org/v1/observations"
            params = {
                "taxon_name": species_name,
                "per_page": 1  # We only need to know if there are any
            }

            # Format the API URL with parameters for logging
            param_str = "&".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()])
            full_url = f"{api_url}?{param_str}"

            log_debug(f"Checking for regular observations with taxon name: {full_url}")
            response = rate_limited_request(api_url, params=params)

            if response.status_code == 200:
                data = response.json()
                total_results = data.get('total_results', 0)

                if total_results > 0:
                    log_debug(f"SUCCESS: Found {total_results} regular observations for taxon name: {species_name}")
                    found_in_main_taxonomy = True
                else:
                    log_debug(f"No regular observations found for taxon name: {species_name}")
            else:
                log_debug(f"iNaturalist observations API returned status code {response.status_code}")

        # STEP 2: Only check provisional names if not found in main taxonomy
        if not found_in_main_taxonomy:
            log_debug(f"\nCHECKING PROVISIONAL NAMES: Checking iNaturalist for provisional species: {species_name}")
            api_url = "https://api.inaturalist.org/v1/observations"
            params = {
                "verifiable": "any",
                "field:Provisional Species Name": species_name
            }

            # Format the API URL with parameters for logging
            param_str = "&".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()])
            full_url = f"{api_url}?{param_str}"
            log_debug(f"Querying iNaturalist provisional observations API: {full_url}")

            response = rate_limited_request(api_url, params=params)

            if response.status_code == 200:
                data = response.json()
                total_results = data.get('total_results', 0)

                if total_results > 0:
                    log_debug(f"SUCCESS: Found {total_results} observations with Provisional Species Name: {species_name}")
                    found_in_provisional = True
                else:
                    log_debug(f"No provisional observations found for: {species_name}")
            else:
                log_debug(f"iNaturalist API returned status code {response.status_code} for provisional check")
        else:
            log_debug(f"Species found in main taxonomy, skipping provisional name check")

        # Return both flags so the process_new_page function knows where it was found
        return {"found": found_in_main_taxonomy or found_in_provisional,
                "main_taxonomy": found_in_main_taxonomy,
                "provisional": found_in_provisional}

    except Exception as e:
        log_debug(f"Error checking iNaturalist: {e}")
        # On error, we'll assume it doesn't exist to be safe
        return {"found": False, "main_taxonomy": False, "provisional": False}

# Edit wiki page to add references section
def edit_page(session, title, content, original_content, summary="Added iNaturalist reference links"):
    # In dry run mode, just print what would happen and return success
    if args.dry_run:
        log_info(f"DRY RUN: Would edit page {title} with summary: {summary}")

        # Find the differences between original and new content
        log_info("--- Content that would be added ---")
        if "== References ==" in content and "== References ==" not in original_content:
            # Extract the references section
            refs_pattern = r"== References ==\n(.*?)(?=(==|\Z))"
            refs_match = re.search(refs_pattern, content, re.DOTALL)
            if refs_match:
                log_info("REFERENCES SECTION:")
                log_info(refs_match.group(0))

        if "== Gallery ==" in content and "== Gallery ==" not in original_content:
            # Extract the gallery section
            gallery_pattern = r"== Gallery ==\n(.*?)(?=(==|\Z))"
            gallery_match = re.search(gallery_pattern, content, re.DOTALL)
            if gallery_match:
                log_info("GALLERY SECTION:")
                log_info(gallery_match.group(0))

        # Check for added links
        if "== References ==" in original_content:
            # Find links in new content that weren't in original
            original_links = set(re.findall(r'\[(https?://[^\s\]]+)[^\]]*\]', original_content))
            new_links = set(re.findall(r'\[(https?://[^\s\]]+)[^\]]*\]', content))
            added_links = new_links - original_links

            if added_links:
                log_info("ADDED LINKS:")
                for link in added_links:
                    # Find the full wiki link format with description
                    link_pattern = r'\[' + re.escape(link) + r'[^\]]*\]'
                    link_matches = re.findall(link_pattern, content)
                    for match in link_matches:
                        if match not in original_content:
                            log_info(match)

        log_info("----------------------------------")
        return True

    # Get edit token
    params = {
        "action": "query",
        "meta": "tokens",
        "format": "json"
    }
    response = session.get(url=WIKI_API_URL, params=params, verify=VERIFY_SSL)
    data = response.json()

    if "query" not in data or "tokens" not in data["query"] or "csrftoken" not in data["query"]["tokens"]:
        log_debug(f"Failed to get edit token: {data}")
        return False

    edit_token = data["query"]["tokens"]["csrftoken"]

    # Edit page
    params = {
        "action": "edit",
        "title": title,
        "text": content,
        "summary": summary,
        "token": edit_token,
        "format": "json"
    }
    response = session.post(WIKI_API_URL, data=params, verify=VERIFY_SSL)
    result = response.json()

    if "error" in result:
        log_debug(f"Error editing page: {result['error']}")
        return False

    log_debug(f"Successfully edited page {title}")
    return True

# Check if References section exists with case-insensitive and spacing-flexible matching
def has_references_section(content):
    # Case-insensitive pattern that matches various spacings
    pattern = r'==\s*references\s*==(\s*\n|$)'
    return bool(re.search(pattern, content, re.IGNORECASE))

# Check if Gallery section exists with case-insensitive and spacing-flexible matching
def has_gallery_section(content):
    # Case-insensitive pattern that matches various spacings
    pattern = r'==\s*gallery\s*==(\s*\n|$)'
    return bool(re.search(pattern, content, re.IGNORECASE))

# Check if References section has a link to MycoMap URL
def has_mycomap_link(content):
    if not has_references_section(content):
        return False

    # Check for links starting with https://mycomap.com/taxonomy
    mycomap_pattern = r'\[https://mycomap\.com/taxonomy/[^\s]+'
    return bool(re.search(mycomap_pattern, content))

# Check if References section has iNaturalist observations link
def has_inaturalist_link(content):
    if not has_references_section(content):
        return False

    # Check for links with "iNaturalist observations" in the description
    inaturalist_pattern = r'\[https://www\.inaturalist\.org/[^\s]+ [^\]]*iNaturalist observations[^\]]*\]'
    return bool(re.search(inaturalist_pattern, content))

# Process new pages and add references and gallery sections if needed
def process_new_page(session, page_title):
    log_info(f"\n========== Processing page: {page_title} ==========")

    # Get page content
    content = get_page_content(session, page_title)
    if not content:
        log_debug(f"Couldn't get content for {page_title}")
        return

    # Extract species name from page title
    species_name = extract_species_name(page_title)
    log_debug(f"Extracted species name: {species_name}")

    # Check if species exists on iNaturalist
    inat_result = check_inaturalist(species_name)

    # If the species isn't found on iNaturalist, don't make any changes
    if not inat_result["found"]:
        log_info(f"Species '{species_name}' not found in iNaturalist. No edits will be made.")
        return

    # Check if page already has a References section
    has_references = has_references_section(content)

    # Check for MycoMap and iNaturalist links
    has_mycomap = has_mycomap_link(content)
    has_inat = has_inaturalist_link(content)

    # Get MycoMap URL (always try to get it if we don't already have it)
    mycomap_url = None
    if not has_mycomap:
        mycomap_url = get_mycomap_url(species_name)
        # Debug output to confirm we got a URL
        if mycomap_url:
            log_debug(f"Successfully retrieved MycoMap URL: {mycomap_url}")
        else:
            log_debug(f"Failed to retrieve a valid MycoMap URL for {species_name}")

    # Check if Gallery section already exists
    has_gallery = has_gallery_section(content)

    # Determine what needs to be added
    need_references = not has_references
    need_inaturalist = not has_inat
    need_mycomap = not has_mycomap and mycomap_url is not None
    need_gallery = not has_gallery

    # If we don't need to make any changes, return early
    if not (need_references or need_inaturalist or need_mycomap or need_gallery):
        log_debug(f"No modifications needed for {page_title}")
        return

    # Save original content for comparison in dry run mode
    original_content = content

    # Start preparing new content
    new_content = content

    # Handle the case where we need to add content to an existing References section
    if has_references and (need_inaturalist or need_mycomap):
        # Find the References section with a case-insensitive pattern
        refs_pattern = r'(==\s*references\s*==)'
        refs_match = re.search(refs_pattern, new_content, re.IGNORECASE)

        if refs_match:
            # Split content at the matched References section
            refs_header = refs_match.group(1)
            parts = new_content.split(refs_header, 1)

            if len(parts) == 2:
                before_refs = parts[0]
                refs_section = refs_header + parts[1]

                # If there's another section after References, split again
                next_section_match = re.search(r'(==\s+[^=]+\s+==)', refs_section[len(refs_header):], re.IGNORECASE)
                refs_parts = None

                if next_section_match:
                    next_section_start = len(refs_header) + next_section_match.start(1)
                    refs_parts = [refs_section[:next_section_start], refs_section[next_section_start:]]
                else:
                    refs_parts = [refs_section, ""]

                # Add new reference links
                updated_refs = refs_parts[0]
                if need_inaturalist:
                    inat_link = prepare_inaturalist_link(species_name, inat_result)
                    if inat_link and inat_link not in updated_refs:
                        if not updated_refs.endswith('\n\n'):
                            updated_refs += '\n'
                        updated_refs += inat_link
                        log_debug(f"Adding iNaturalist link to existing References section")

                if need_mycomap and mycomap_url:
                    mycomap_link = f"* [{mycomap_url} Mycomap page for {species_name}]\n"
                    if mycomap_link not in updated_refs:
                        if not updated_refs.endswith('\n\n'):
                            updated_refs += '\n'
                        updated_refs += mycomap_link
                        log_debug(f"Adding MycoMap link to existing References section: {mycomap_link}")

                # Ensure proper spacing between sections
                if refs_parts[1] and not updated_refs.endswith('\n\n'):
                    updated_refs += '\n'

                # Combine everything back
                new_content = before_refs + updated_refs + refs_parts[1]
            else:
                log_debug(f"ERROR: Failed to split content at References section for {page_title}")
                return
        else:
            log_debug(f"ERROR: Failed to find References section pattern for {page_title}")
            return
    else:
        # Add new sections as needed
        # Make sure content ends with newlines for clean section additions
        if not new_content.endswith("\n\n"):
            new_content = new_content.rstrip("\n") + "\n\n"

        # Add references section if needed
        if need_references:
            references_content = "== References ==\n"

            # Add iNaturalist link
            if need_inaturalist:
                references_content += prepare_inaturalist_link(species_name, inat_result)

            # Add MycoMap link if available
            if need_mycomap and mycomap_url:
                mycomap_link = f"* [{mycomap_url} Mycomap page for {species_name}]\n"
                references_content += mycomap_link
                log_debug(f"Adding MycoMap link to new References section: {mycomap_link}")

            # Ensure proper spacing
            references_content += "\n"
            new_content += references_content

        # Add gallery section if needed (always last)
        if need_gallery:
            gallery_content = "== Gallery ==\n\n<iNaturalistGallery />\n\n"
            new_content += gallery_content

    # Prepare summary for the edit
    summary = []
    if need_references:
        summary.append("Added References section")
    if need_inaturalist:
        summary.append("Added iNaturalist link")
    if need_mycomap:
        summary.append("Added MycoMap link")
    if need_gallery:
        summary.append("Added Gallery section")

    edit_summary = ", ".join(summary)

    # Log changes that will be made
    changes = []
    if need_references:
        changes.append("references section")
    if need_inaturalist:
        changes.append("iNaturalist link")
    if need_mycomap:
        changes.append("MycoMap link")
    if need_gallery:
        changes.append("gallery section")

    # Only proceed if we have changes to make
    if changes:
        action = "DRY RUN: Would add" if args.dry_run else "Adding"
        log_info(f"{action} {', '.join(changes)} to {page_title}")

        # Make the edit
        success = edit_page(session, page_title, new_content, original_content, summary=edit_summary)

        if not success:
            log_info(f"Failed to update {page_title}")
    else:
        log_info(f"No changes needed for {page_title}")

# Helper function to prepare the iNaturalist link
def prepare_inaturalist_link(species_name, result):
    encoded_name = urllib.parse.quote(species_name)

    if not result or not result["found"]:
        return ""

    # Determine which links to add based on where the species was found
    if result["main_taxonomy"]:
        return f"* [https://www.inaturalist.org/observations?taxon_name={encoded_name}&field:DNA%20Barcode%20ITS Sequenced iNaturalist observations of {species_name}]\n"
    elif result["provisional"]:
        return f"* [https://www.inaturalist.org/observations?verifiable=any&place_id=any&field:Provisional%20Species%20Name={encoded_name} iNaturalist observations of provisional species name {species_name}]\n"

    return ""

# Main function to periodically check for new pages
def main():
    log_info("Starting iNaturalist reference bot...")
    if args.dry_run:
        log_info("Running in DRY RUN mode - no actual changes will be made to the wiki")
    log_info("Press Ctrl+C to stop")

    last_check_time = None

    try:
        while True:
            log_debug(f"\nChecking for new pages since {last_check_time}")

            # Login to the wiki
            session = wiki_login()
            if not session:
                log_debug("Failed to login. Retrying in 5 minutes.")
                time.sleep(300)
                continue

            # Get new pages
            new_pages = get_new_pages(session, last_check_time)
            log_debug(f"Found {len(new_pages)} new pages")

            # Process each new page
            for page in new_pages:
                process_new_page(session, page["title"])

            # Update last check time
            if new_pages:
                last_check_time = new_pages[0]["timestamp"]

            # Sleep until next check
            log_info(f"Next check in {CHECK_INTERVAL/60} minutes")
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        log_info("\nBot stopped by user")
    except Exception as e:
        log_info(f"Error: {e}")
        log_info("Bot crashed, please check the error and restart")

if __name__ == "__main__":
    main()
