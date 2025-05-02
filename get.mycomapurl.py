#!/usr/bin/python3

# Convert a name to a Mycomap URL

# Alan Rockefeller April 30, 2025

import requests
from bs4 import BeautifulSoup
import argparse

def get_mycomap_taxonomy_url(species_name, debug=False):
    base_url = "https://mycomap.com"
    taxonomy_url = f"{base_url}/taxonomy"
    # Create a session with the MycoMap
    session = requests.Session()
    # Step 1: Make the POST request instead of GET, adding User-Agent and other headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = {
        'do': 'findByName',
        'input': species_name,
        'csrfKey': 'ignore'  # doesn't matter if session is valid
    }
    
    if debug:
        print(f"Searching for species: {species_name}")
    
    try:
        response = session.post(
            taxonomy_url,
            headers=headers,
            data=data,
            timeout=10,          # fail fast
        )
        response.raise_for_status()
    except requests.RequestException as err:
        if debug:
            print(f"Request to {taxonomy_url} failed: {err}")
        return None
    
    # Debugging info only if debug flag is set
    if debug:
        print(f"Search status: {response.status_code}")
        print("Response headers:", response.headers)
        print("\n=== RAW HTML ===")
        print(response.text[:5000])  # Print only first 5000 chars
        print("=== END HTML ===")
    
    # Step 2: Parse the HTML for the species link
    soup = BeautifulSoup(response.text, 'html.parser')
    species_div = soup.find('div', class_='ipsGrid_span3')
    if species_div:
        link = species_div.find('a', href=True)
        if link:
            href = link['href']
            # Check if href already starts with the base_url
            if href.startswith(base_url):
                return href
            else:
                return base_url + href
    
    if debug:
        print("No taxonomy result found.")
    
    return None

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Get MycoMap taxonomy URL for a species')
    parser.add_argument('species', help='Species name to search for')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Get URL with debug flag
    url = get_mycomap_taxonomy_url(args.species, args.debug)
    
    # Only output the URL (or None)
    if url:
        print(url)
    else:
        print("No URL found")

if __name__ == "__main__":
    main()
