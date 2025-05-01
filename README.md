# Initial Commit
=======
# Mycomap Wiki Taxonomy Bot

**Version:** 1.0  
**Author:** Alan Rockefeller  
**Date:** May 1, 2025  
**GitHub:** [http://github.com/AlanRockefeller/taxonomybot.py](http://github.com/AlanRockefeller/taxonomybot.py)  
**Wiki:** [http://mycomap.org](http://mycomap.org)

## Overview

This bot automatically updates wiki pages for fungal species on the [MycoMap](https://mycomap.org) wiki. It monitors recently created pages and adds standardized references and gallery sections that connect the wiki entries to external taxonomic resources on Mycomap.com and iNaturalist.org.

## Features

The bot performs the following tasks:

1. **Species Validation**: Verifies if the page title represents a valid fungal species by checking against iNaturalist's taxonomy database.  If the name isn't found in the standard iNaturalist taxonomy, it checks to see if the name of the wiki page is in use as a Provisional Species Name on iNaturalist.   If neither matches, the wiki page is assumed to be a page that isn't about a fungal species.

2. **References Section**: Adds a standardized "References" section if one doesn't exist, including:
   - iNaturalist observation links (either from main taxonomy or provisional species)
   - MycoMap taxonomy links (retrieved from the MycoMap database)

3. **Gallery Section**: Adds a standard "Gallery" section with the `<iNaturalistGallery />` tag to display photos of relevent observations from inaturalist.   The iNaturalistGallery extension is available here:  https://github.com/MatejFranceskin/iNaturalistGallery

## How It Works

1. The bot periodically checks for newly created wiki pages.
2. For each new page, it extracts the species name from the page title.
3. It verifies the species exists in iNaturalist (either in main taxonomy or as a provisional species).
4. It checks if the page already has References and Gallery sections.
5. It retrieves the corresponding MycoMap taxonomy URL using `/home/wikibot/get.mycomapurl.py`.
6. It adds any missing sections or links to the page.

## Example Changes

For a new species page Daldinia "sp-IN02", the bot would add:

```
== References ==
* [https://www.inaturalist.org/observations?verifiable=any&place_id=any&field:Provisional%20Species%20Name=Daldinia%20%22sp-IN02%22 iNaturalist observations for provisional species name Daldinia "sp-IN02"]
* [https://mycomap.com/taxonomy/562152-daldinia-sp-in02/ Mycomap page for Daldinia "sp-IN02"]

== Gallery ==

<iNaturalistGallery />
```

## Command Line Options

The bot supports the following command line options:

* `--dry-run`: Shows what changes would be made without actually making edits
* `--debug`: Displays detailed debugging information

## Configuration

The bot uses a configuration section at the top of the script for customizing:

* Wiki API URLs
* Login credentials
* Check interval (default: hourly)
* Paths to external scripts

## Dependencies

* Python 3.9+
* BeautifulSoup4 (automatically installed if missing)
* Requests library
* `/home/wikibot/bin/get.mycomapurl.py` script for MycoMap taxonomy URLs

## Installation

1. Place the script in `/home/wikibot/` directory
2. Ensure `/home/wikibot/bin/get.mycomapurl.py` exists and is executable
3. Set up a systemd service to start the script on boot

## Running the Bot

Basic usage:
```
python3 wiki_taxonomy_bot.py
```

With options:
```
python3 wiki_taxonomy_bot.py --dry-run --debug
```

## Contributing

Contributions to improve the bot are welcome! You can contribute in two ways:

1. **GitHub Pull Requests**: Submit improvements or bug fixes via pull requests to the [GitHub repository](http://github.com/AlanRockefeller/taxonomybot.py).

2. **Direct Contact**: For suggestions, feedback, or to report issues, please contact Alan Rockefeller via email or message on iNaturalist, Facebook, LinkedIn, Instagram, etc.

When contributing code, please:
- Include clear comments
- Update the README if adding new features

## License

This code is distributed under the GNU GPL 3.0 license
