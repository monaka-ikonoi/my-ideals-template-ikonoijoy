#!/usr/bin/env python3
"""
Image Downloader Script
Downloads images from #subphotoimg > li > .imgBig selector
Also supports range-based downloads for numeric filenames

Usage:
    python3 download_images.py <URL> <directory> [filenames]
    python3 download_images.py <URL> <directory> -r <range>
    python3 download_images.py <URL> <directory> -r <range> -s <suffix>
    
Examples:
    python3 download_images.py 'https://example.com' 'images'
    python3 download_images.py 'https://example.com' 'photos' '01.jpg,02.jpg,03.jpg'
    python3 download_images.py 'https://storage.googleapis.com/.../685.jpg' 'images' -r 3
    python3 download_images.py 'https://example.com/prefix_01.jpg' 'images' -r 12
    python3 download_images.py 'https://example.com/prefix_01_500.jpg' 'images' -r 2 -s '_500'
"""

import sys
import os
import argparse
import requests
import json
import hashlib
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path
from datetime import datetime, timezone


class ImageDownloader:
    def __init__(self, url, directory, filenames=None, range_count=None, suffix=None, verbose=True):
        """
        Initialize the image downloader
        
        Args:
            url: Target webpage URL or direct image URL
            directory: Directory to save images
            filenames: Optional comma-separated filename list
            range_count: Number of images to download in range mode
            suffix: Optional suffix after the number (e.g., '_500')
            verbose: Print detailed output
        """
        self.url = url
        self.directory = directory
        self.filenames = self._parse_filenames(filenames)
        self.range_count = range_count
        self.suffix = suffix
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.metadata = []  # Store metadata for each downloaded image
        self.is_range_mode = False
    
    def _parse_filenames(self, filenames):
        """Parse comma-separated filenames into a list"""
        if not filenames:
            return []
        return [name.strip() for name in filenames.split(',') if name.strip()]
    
    def _print(self, message, end='\n'):
        """Print message if verbose mode is enabled"""
        if self.verbose:
            print(message, end=end)
    
    def calculate_sha256(self, filepath):
        """Calculate SHA256 checksum of a file"""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            # Read file in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def is_direct_image_url(self, url):
        """Check if URL points directly to an image file"""
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
        parsed = urlparse(url)
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in image_extensions)
    
    def extract_numeric_pattern(self, url):
        """
        Extract numeric pattern from URL
        Returns (base_url, prefix, number, suffix, extension, digit_width, pattern_type) or None
        
        Supports four patterns (in priority order):
        1. Suffix pattern (when --suffix is provided): prefix_01_500.jpg
        2. Underscore pattern: prefix_01.jpg
        3. Letter-number pattern: jsuetrki00.jpg
        4. Simple pattern: 685.jpg
        
        Examples:
            Input: https://example.com/1711_love_photo_01_500.jpg (with suffix='_500')
            Output: ('https://example.com/', '1711_love_photo_', 1, '_500', '.jpg', 2, 'suffix')
            
            Input: https://example.com/2110_me_photo_1stconcert1024_dkwotbas_01.jpg
            Output: ('https://example.com/', '2110_me_photo_1stconcert1024_dkwotbas_', 1, '', '.jpg', 2, 'underscore')
            
            Input: https://example.com/2110_love_photo_9thcw20211031_jsuetrki00.jpg
            Output: ('https://example.com/', '2110_love_photo_9thcw20211031_jsuetrki', 0, '', '.jpg', 2, 'letter_number')
            
            Input: https://storage.googleapis.com/.../685.jpg
            Output: ('https://storage.googleapis.com/.../', '', 685, '', '.jpg', 3, 'simple')
        """
        parsed = urlparse(url)
        path = parsed.path
        
        # Extract filename from path
        filename = os.path.basename(path)
        base_path = os.path.dirname(path) + '/'
        
        # Reconstruct base URL
        base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"
        
        # Pattern 0: Suffix pattern (when --suffix is provided) - Highest priority
        # Match: prefix_01_500.jpg where _500 is the user-provided suffix
        if self.suffix:
            # Escape special regex characters in suffix
            escaped_suffix = re.escape(self.suffix)
            
            # Build pattern: (.+_)(digits)(suffix)(.ext)
            # Prefix must end with underscore before the number
            pattern = rf'^(.+_)(\d+)({escaped_suffix})(\.\w+)$'
            match_suffix = re.match(pattern, filename)
            
            if match_suffix:
                prefix = match_suffix.group(1)
                number_str = match_suffix.group(2)
                number = int(number_str)
                suffix_matched = match_suffix.group(3)
                extension = match_suffix.group(4)
                digit_width = len(number_str)
                
                return (base_url, prefix, number, suffix_matched, extension, digit_width, 'suffix')
            
            # Also try pattern without underscore before number
            # Match: prefixABC01_500.jpg
            pattern2 = rf'^(.+[a-zA-Z])(\d+)({escaped_suffix})(\.\w+)$'
            match_suffix2 = re.match(pattern2, filename)
            
            if match_suffix2:
                prefix = match_suffix2.group(1)
                number_str = match_suffix2.group(2)
                number = int(number_str)
                suffix_matched = match_suffix2.group(3)
                extension = match_suffix2.group(4)
                digit_width = len(number_str)
                
                return (base_url, prefix, number, suffix_matched, extension, digit_width, 'suffix')
        
        # Pattern 1: filename_number.ext (underscore pattern)
        # Match: prefix_01.jpg, file_name_123.png, etc.
        # Must have underscore immediately before number
        match_underscore = re.match(r'^(.+_)(\d+)(\.\w+)$', filename)
        
        if match_underscore:
            prefix = match_underscore.group(1)
            number_str = match_underscore.group(2)
            number = int(number_str)
            extension = match_underscore.group(3)
            digit_width = len(number_str)
            
            return (base_url, prefix, number, '', extension, digit_width, 'underscore')
        
        # Pattern 2: prefix[letters]number.ext (letter-number pattern)
        # Match: jsuetrki00.jpg, photo123.png, etc.
        # Must end with letter(s) followed by number(s)
        match_letter_number = re.match(r'^(.+[a-zA-Z])(\d+)(\.\w+)$', filename)
        
        if match_letter_number:
            prefix = match_letter_number.group(1)
            number_str = match_letter_number.group(2)
            number = int(number_str)
            extension = match_letter_number.group(3)
            digit_width = len(number_str)
            
            return (base_url, prefix, number, '', extension, digit_width, 'letter_number')
        
        # Pattern 3: number.ext (simple pattern)
        # Match: 685.jpg, 001.png, etc.
        # Pure numeric filename
        match_simple = re.match(r'^(\d+)(\.\w+)$', filename)
        
        if match_simple:
            number_str = match_simple.group(1)
            number = int(number_str)
            extension = match_simple.group(2)
            digit_width = len(number_str)
            
            return (base_url, '', number, '', extension, digit_width, 'simple')
        
        return None
    
    def generate_range_urls(self, base_url, prefix, start_number, suffix, extension, count, digit_width):
        """Generate URLs for range download"""
        urls = []
        for i in range(count):
            number = start_number + i
            # Format with leading zeros if original had them
            number_str = str(number).zfill(digit_width)
            
            # Construct filename based on pattern
            filename = f"{prefix}{number_str}{suffix}{extension}"
            
            url = f"{base_url}{filename}"
            urls.append(url)
        return urls
    
    def fetch_page(self):
        """Fetch the webpage content"""
        self._print("Fetching webpage...")
        try:
            response = self.session.get(self.url, timeout=30)
            response.raise_for_status()
            self._print(f"✓ Successfully fetched page (Status: {response.status_code})")
            return response.text
        except requests.exceptions.RequestException as e:
            self._print(f"✗ Error fetching page: {e}")
            sys.exit(1)
    
    def extract_image_urls(self, html):
        """Extract image URLs from HTML using BeautifulSoup"""
        self._print("Parsing HTML...")
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find images: #subphotoimg > li > .imgBig
        images = soup.select('#subphotoimg > li > .imgBig')
        
        if not images:
            self._print("✗ No images found with selector '#subphotoimg > li > .imgBig'")
            sys.exit(1)
        
        image_urls = []
        for img in images:
            src = img.get('src')
            if src:
                # Convert relative URLs to absolute
                full_url = urljoin(self.url, src)
                image_urls.append(full_url)
        
        self._print(f"✓ Found {len(image_urls)} images")
        return image_urls
    
    def get_image_urls(self):
        """Get image URLs based on mode (webpage or range)"""
        # Check if URL is a direct image and range mode is enabled
        if self.range_count and self.is_direct_image_url(self.url):
            pattern = self.extract_numeric_pattern(self.url)
            
            if pattern:
                self.is_range_mode = True
                base_url, prefix, start_number, suffix, extension, digit_width, pattern_type = pattern
                
                self._print(f"Range mode detected:")
                self._print(f"  Pattern type: {pattern_type}")
                self._print(f"  Base URL: {base_url}")
                if prefix:
                    self._print(f"  Filename prefix: {prefix}")
                self._print(f"  Starting number: {start_number}")
                if suffix:
                    self._print(f"  Filename suffix: {suffix}")
                self._print(f"  Extension: {extension}")
                self._print(f"  Digit width: {digit_width} (preserving leading zeros)")
                self._print(f"  Range: {self.range_count} images")
                self._print("")
                
                urls = self.generate_range_urls(base_url, prefix, start_number, suffix, extension, self.range_count, digit_width)
                self._print(f"✓ Generated {len(urls)} URLs")
                
                # Print the URLs for verification
                if self.verbose:
                    for i, url in enumerate(urls):
                        filename = os.path.basename(url)
                        self._print(f"  [{i+1}] {filename}")
                    self._print("")
                
                return urls
            else:
                self._print("Warning: Range mode requested but no numeric pattern found in URL")
                if self.suffix:
                    self._print(f"  Tried to match suffix '{self.suffix}' but failed")
                self._print("Falling back to single image download")
                return [self.url]
        
        # Direct image URL without range
        elif self.is_direct_image_url(self.url):
            self._print("Direct image URL detected")
            return [self.url]
        
        # Webpage mode
        else:
            html = self.fetch_page()
            return self.extract_image_urls(html)
    
    def create_directory(self):
        """Create the target directory if it doesn't exist"""
        Path(self.directory).mkdir(parents=True, exist_ok=True)
        self._print(f"✓ Directory created/verified: {self.directory}")
    
    def get_filename(self, url, index):
        """Determine the filename for an image"""
        if index < len(self.filenames) and self.filenames[index]:
            return self.filenames[index]
        else:
            # Extract filename from URL, remove query parameters
            return os.path.basename(url).split('?')[0]
    
    def download_image(self, url, filepath, index, total):
        """Download a single image and collect metadata"""
        filename = os.path.basename(filepath)
        self._print(f"[{index + 1}/{total}] Downloading: {filename}... ", end='')
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            size = os.path.getsize(filepath)
            size_str = self._format_size(size)
            
            # Calculate SHA256
            sha256 = self.calculate_sha256(filepath)
            
            # Store metadata (without size_human)
            self.metadata.append({
                "file": filename,
                "source": url,
                "sha256": sha256,
                "size": size
            })
            
            self._print(f"✓ Done ({size_str})")
            return True
            
        except requests.exceptions.RequestException as e:
            self._print(f"✗ Failed: {e}")
            return False
        except Exception as e:
            self._print(f"✗ Error: {e}")
            return False
    
    def _format_size(self, size):
        """Format file size in human-readable format"""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / 1024 / 1024:.1f}MB"
    
    def save_metadata(self):
        """Save metadata to JSON file"""
        metadata_path = os.path.join(self.directory, 'metadata.json')
        
        # Get current UTC time with timezone info
        utc_now = datetime.now(timezone.utc)
        
        metadata_output = {
            "generated_at": utc_now.isoformat(),
            "source_url": self.url,
            "mode": "range" if self.is_range_mode else "webpage",
            "total_images": len(self.metadata),
            "images": self.metadata
        }
        
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata_output, f, indent=2, ensure_ascii=False)
            
            self._print(f"✓ Metadata saved to: {metadata_path}")
            return True
        except Exception as e:
            self._print(f"✗ Failed to save metadata: {e}")
            return False
    
    def download_all(self):
        """Main download process"""
        self._print("=" * 60)
        self._print("Image Downloader")
        self._print("=" * 60)
        self._print(f"Source URL: {self.url}")
        self._print(f"Save to: {self.directory}")
        
        if self.range_count:
            self._print(f"Range mode: Download {self.range_count} images")
            if self.suffix:
                self._print(f"Suffix pattern: {self.suffix}")
        elif self.filenames:
            self._print(f"Custom filenames: {len(self.filenames)} provided")
        else:
            self._print("Using original filenames")
        
        self._print("")
        
        # Create directory
        self.create_directory()
        
        # Get image URLs
        image_urls = self.get_image_urls()
        
        self._print("")
        self._print("Starting downloads...")
        self._print("=" * 60)
        
        # Download images
        success_count = 0
        failed_count = 0
        
        for i, url in enumerate(image_urls):
            filename = self.get_filename(url, i)
            filepath = os.path.join(self.directory, filename)
            
            if self.download_image(url, filepath, i, len(image_urls)):
                success_count += 1
            else:
                failed_count += 1
        
        # Save metadata
        self._print("=" * 60)
        self._print("Generating metadata...")
        self.save_metadata()
        
        # Summary
        self._print("=" * 60)
        self._print(f"✓ Download complete!")
        self._print(f"  Total: {len(image_urls)} images")
        self._print(f"  Success: {success_count}")
        if failed_count > 0:
            self._print(f"  Failed: {failed_count}")
        self._print(f"  Location: {os.path.abspath(self.directory)}/")
        
        return success_count, failed_count


def main():
    parser = argparse.ArgumentParser(
        description='Download images from webpage or by URL range',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download from webpage with selector
  %(prog)s 'https://example.com/page' 'images'
  
  # Download with custom filenames
  %(prog)s 'https://example.com/page' 'photos' -n '01.jpg,02.jpg,03.jpg'
  
  # Range download - Simple numeric pattern
  %(prog)s 'https://storage.googleapis.com/.../685.jpg' 'images' -r 3
  # Downloads: 685.jpg, 686.jpg, 687.jpg
  
  # Range download - Underscore pattern
  %(prog)s 'https://example.com/.../prefix_01.jpg' 'images' -r 12
  # Downloads: prefix_01.jpg, prefix_02.jpg, ..., prefix_12.jpg
  
  # Range download - Letter-number pattern
  %(prog)s 'https://example.com/.../jsuetrki00.jpg' 'images' -r 2
  # Downloads: jsuetrki00.jpg, jsuetrki01.jpg
  
  # Range download - With suffix pattern
  %(prog)s 'https://example.com/.../1711_love_photo_01_500.jpg' 'images' -r 2 -s '_500'
  # Downloads: 1711_love_photo_01_500.jpg, 1711_love_photo_02_500.jpg
  
  %(prog)s 'https://example.com/.../image01_large.jpg' 'images' -r 3 -s '_large'
  # Downloads: image01_large.jpg, image02_large.jpg, image03_large.jpg
  
  # Quiet mode
  %(prog)s 'https://example.com/page' 'images' -q
        """
    )
    
    parser.add_argument('url', help='Target webpage URL or direct image URL')
    parser.add_argument('directory', help='Directory to save images')
    parser.add_argument('filenames', nargs='?', default=None,
                        help='Comma-separated filename list (optional)')
    parser.add_argument('-n', '--names', dest='filenames_alt',
                        help='Alternative way to specify filenames')
    parser.add_argument('-r', '--range', type=int, dest='range_count',
                        help='Download range (for numeric filenames, e.g., -r 3 downloads 3 images)')
    parser.add_argument('-s', '--suffix', dest='suffix',
                        help='Suffix after the number (e.g., -s "_500" for prefix_01_500.jpg)')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Quiet mode (minimal output)')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s 1.4')
    
    args = parser.parse_args()
    
    # Handle filename argument (support both positional and --names)
    filenames = args.filenames or args.filenames_alt
    
    # Run downloader
    downloader = ImageDownloader(
        url=args.url,
        directory=args.directory,
        filenames=filenames,
        range_count=args.range_count,
        suffix=args.suffix,
        verbose=not args.quiet
    )
    
    success, failed = downloader.download_all()
    
    # Exit with error code if any downloads failed
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
