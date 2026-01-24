#!/usr/bin/env python3
"""
Split composite images into individual sub-images.
Usage: python split_image.py input output [options]
"""

import os
import argparse
from PIL import Image
import numpy as np

# Supported input formats
INPUT_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.gif'}


def trim_white_border(img_array, brightness_threshold=250, white_ratio=0.85, max_trim=10, sides="tblr"):
    """
    Trim white borders from image edges.
    
    Args:
        sides: String containing which sides to trim:
               t=top, b=bottom, l=left, r=right
               e.g., "lr" = only left and right, "tblr" = all sides
    """
    height, width = img_array.shape[:2]
    
    def is_edge_white(pixels):
        brightness = np.mean(pixels, axis=-1)
        bright_pixel_ratio = np.mean(brightness > brightness_threshold)
        return bright_pixel_ratio >= white_ratio
    
    top = bottom = left = right = 0
    sides = sides.lower()
    
    # Top
    if 't' in sides:
        for i in range(min(max_trim, height // 4)):
            if is_edge_white(img_array[i, :, :]):
                top = i + 1
            else:
                break
    
    # Bottom
    if 'b' in sides:
        for i in range(min(max_trim, height // 4)):
            if is_edge_white(img_array[height - 1 - i, :, :]):
                bottom = i + 1
            else:
                break
    
    # Left
    if 'l' in sides:
        for i in range(min(max_trim, width // 4)):
            if is_edge_white(img_array[:, i, :]):
                left = i + 1
            else:
                break
    
    # Right
    if 'r' in sides:
        for i in range(min(max_trim, width // 4)):
            if is_edge_white(img_array[:, width - 1 - i, :]):
                right = i + 1
            else:
                break
    
    return top, bottom, left, right


def generate_output_filename(base_name, row, col, total_cols, suffix_template, suffix_list):
    """Generate output filename based on template or suffix list."""
    n = row * total_cols + col
    
    if suffix_list:
        suffix = suffix_list[n % len(suffix_list)]
        return f"{base_name}{suffix}"
    
    return suffix_template.format(
        name=base_name,
        row=row,
        col=col,
        n=n,
        N=n + 1
    )


def save_image(img, output_path, output_format, quality=95):
    """Save image in specified format."""
    format_lower = output_format.lower().lstrip('.')
    
    if format_lower in ('jpg', 'jpeg'):
        img = img.convert('RGB')
        img.save(output_path, 'JPEG', quality=quality)
    elif format_lower == 'png':
        img.save(output_path, 'PNG')
    elif format_lower == 'webp':
        img.save(output_path, 'WEBP', quality=quality)
    else:
        img.save(output_path, quality=quality)


def split_composite_image(image_path, output_dir, white_threshold=245, 
                          min_size=50, min_gap=3, white_ratio=0.98,
                          trim=False, trim_max=10, trim_threshold=248,
                          trim_sides="tblr",
                          suffix_template="{name}_{row}_{col}",
                          suffix_list=None, output_format="jpg", quality=95):
    """Split a composite image into individual sub-images."""
    img = Image.open(image_path).convert('RGB')
    arr = np.array(img)
    height, width = arr.shape[:2]
    
    def is_white_column(col):
        column_pixels = arr[:, col, :]
        pixel_is_white = np.all(column_pixels > white_threshold, axis=1)
        return np.mean(pixel_is_white) >= white_ratio
    
    def is_white_row(row):
        row_pixels = arr[row, :, :]
        pixel_is_white = np.all(row_pixels > white_threshold, axis=1)
        return np.mean(pixel_is_white) >= white_ratio
    
    def find_regions(axis_size, is_white_func):
        is_white = [is_white_func(i) for i in range(axis_size)]
        
        regions = []
        in_region = False
        start = 0
        
        for i in range(axis_size):
            if not is_white[i] and not in_region:
                start = i
                in_region = True
            elif is_white[i] and in_region:
                gap_end = i
                while gap_end < axis_size and is_white[gap_end]:
                    gap_end += 1
                
                if gap_end - i >= min_gap or gap_end == axis_size:
                    if i - start >= min_size:
                        regions.append((start, i))
                    in_region = False
        
        if in_region and axis_size - start >= min_size:
            regions.append((start, axis_size))
        
        return regions
    
    h_regions = find_regions(width, is_white_column)
    v_regions = find_regions(height, is_white_row)
    
    if not v_regions:
        v_regions = [(0, height)]
    if not h_regions:
        h_regions = [(0, width)]
    
    print(f"  Detected {len(h_regions)} cols x {len(v_regions)} rows")
    
    total_images = len(h_regions) * len(v_regions)
    if suffix_list and len(suffix_list) < total_images:
        print(f"  Warning: suffix list ({len(suffix_list)}) < slices ({total_images}), will cycle")
    
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    output_ext = f".{output_format.lower().lstrip('.')}"
    
    count = 0
    for vi, (y1, y2) in enumerate(v_regions):
        for hi, (x1, x2) in enumerate(h_regions):
            crop_x1, crop_y1, crop_x2, crop_y2 = x1, y1, x2, y2
            
            if trim:
                sub_arr = arr[y1:y2, x1:x2, :]
                top, bottom, left, right = trim_white_border(
                    sub_arr, 
                    brightness_threshold=trim_threshold,
                    white_ratio=0.80,
                    max_trim=trim_max,
                    sides=trim_sides
                )
                crop_x1 += left
                crop_x2 -= right
                crop_y1 += top
                crop_y2 -= bottom
                
                trim_info = ""
                if any([top, bottom, left, right]):
                    trim_info = f" (trim: T{top} B{bottom} L{left} R{right})"
            else:
                trim_info = ""
            
            cropped = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
            
            output_name = generate_output_filename(
                base_name, vi, hi, len(h_regions), 
                suffix_template, suffix_list
            )
            output_path = os.path.join(output_dir, output_name + output_ext)
            
            save_image(cropped, output_path, output_format, quality)
            count += 1
            
            final_w = crop_x2 - crop_x1
            final_h = crop_y2 - crop_y1
            print(f"    [{vi},{hi}] {final_w}x{final_h}{trim_info} -> {output_name}{output_ext}")
    
    return count


def process_directory(input_dir, output_dir, recursive=False, **kwargs):
    """Process images in a directory."""
    total = 0
    
    if recursive:
        for root, dirs, files in os.walk(input_dir):
            rel_path = os.path.relpath(root, input_dir)
            if rel_path == ".":
                rel_path = ""
            
            current_output_dir = os.path.join(output_dir, rel_path) if rel_path else output_dir
            
            image_files = [f for f in sorted(files) 
                          if os.path.splitext(f)[1].lower() in INPUT_EXTENSIONS]
            
            if image_files:
                if rel_path:
                    print(f"\n[Dir] {rel_path}")
                
                for filename in image_files:
                    image_path = os.path.join(root, filename)
                    print(f"Processing: {filename}")
                    count = split_composite_image(
                        image_path, 
                        current_output_dir, 
                        **kwargs
                    )
                    total += count
    else:
        for filename in sorted(os.listdir(input_dir)):
            if os.path.splitext(filename)[1].lower() in INPUT_EXTENSIONS:
                image_path = os.path.join(input_dir, filename)
                print(f"Processing: {filename}")
                count = split_composite_image(
                    image_path,
                    output_dir,
                    **kwargs
                )
                total += count
    
    return total


def parse_suffix_list(suffix_str):
    """Parse suffix list string (comma or space separated)."""
    if not suffix_str:
        return None
    
    if ',' in suffix_str:
        return [s.strip() for s in suffix_str.split(',')]
    
    return suffix_str.split()


def main():
    parser = argparse.ArgumentParser(
        description='Split composite images into individual sub-images',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Naming Options (mutually exclusive):

  1. Suffix list --suffixes: specify suffix for each slice
     --suffixes="_a,_b,_c"           -> photo_a.jpg, photo_b.jpg, photo_c.jpg
     --suffixes="-foo,-bar,-baz"     -> photo-foo.jpg, photo-bar.jpg, photo-baz.jpg
     
     NOTE: Use "=" when suffixes start with "-" to avoid argument parsing issues.

  2. Template --suffix: use variables to generate names
     --suffix "{name}_{N}"           -> photo_1.jpg, photo_2.jpg
     
     Template variables:
       {name}  original filename (without extension)
       {row}   row index (from 0)
       {col}   column index (from 0)
       {n}     sequence number (from 0)
       {N}     sequence number (from 1)

Trim Sides:
  --trim-sides accepts combination of: t(top), b(bottom), l(left), r(right)
  
  Examples:
    --trim-sides tblr   trim all sides (default)
    --trim-sides lr     trim left and right only
    --trim-sides tb     trim top and bottom only
    --trim-sides lrb    trim left, right, and bottom (not top)

Examples:
  %(prog)s input.jpg output
  %(prog)s input.jpg output --suffixes="_a,_b,_c"
  %(prog)s input.jpg output --trim --trim-sides lr
  %(prog)s ./input ./output -R --trim --trim-sides lrb
  %(prog)s ./input ./output -R --suffixes="_a,_b,_c" -e webp -q 90
        '''
    )
    
    parser.add_argument('input', help='Input image file or directory')
    parser.add_argument('output', help='Output directory')
    
    # Directory options
    parser.add_argument('-R', '--recursive', action='store_true',
                        help='Recursively process subdirectories, preserving structure')
    
    # Separator detection
    parser.add_argument('-t', '--threshold', type=int, default=245,
                        help='White pixel threshold (0-255), default: 245')
    parser.add_argument('-s', '--min-size', type=int, default=50,
                        help='Minimum sub-image size in pixels, default: 50')
    parser.add_argument('-g', '--min-gap', type=int, default=3,
                        help='Minimum separator width in pixels, default: 3')
    parser.add_argument('-r', '--white-ratio', type=float, default=0.99,
                        help='White pixel ratio threshold for separator detection, default: 0.99')
    
    # Border trimming
    parser.add_argument('--trim', action='store_true',
                        help='Enable white border trimming')
    parser.add_argument('--trim-max', type=int, default=10,
                        help='Maximum pixels to trim per edge, default: 10')
    parser.add_argument('--trim-t', type=int, default=248,
                        help='Brightness threshold for trimming, default: 248')
    parser.add_argument('--trim-sides', type=str, default="tblr",
                        help='Sides to trim: t(top), b(bottom), l(left), r(right), default: tblr')
    
    # Output naming
    naming_group = parser.add_mutually_exclusive_group()
    naming_group.add_argument('--suffixes', type=str, default=None,
                              help='Comma-separated suffix list, e.g., --suffixes="_a,_b,_c"')
    naming_group.add_argument('--suffix', type=str, default="{name}_{row}_{col}",
                              help='Filename template, default: "{name}_{row}_{col}"')
    
    # Output format
    parser.add_argument('-e', '--format', type=str, default="webp",
                        choices=['jpg', 'png', 'webp'],
                        help='Output format: jpg, png, webp (default: webp)')
    parser.add_argument('-q', '--quality', type=int, default=95,
                        help='Output quality for jpg/webp (1-100), default: 95')
    
    args = parser.parse_args()
    
    # Validate trim-sides
    valid_sides = set('tblr')
    if not all(c in valid_sides for c in args.trim_sides.lower()):
        parser.error(f"--trim-sides must only contain t, b, l, r (got: {args.trim_sides})")
    
    suffix_list = parse_suffix_list(args.suffixes)
    
    common_args = {
        'white_threshold': args.threshold,
        'min_size': args.min_size,
        'min_gap': args.min_gap,
        'white_ratio': args.white_ratio,
        'trim': args.trim,
        'trim_max': args.trim_max,
        'trim_threshold': args.trim_t,
        'trim_sides': args.trim_sides,
        'suffix_template': args.suffix,
        'suffix_list': suffix_list,
        'output_format': args.format,
        'quality': args.quality,
    }
    
    # Format trim sides for display
    sides_display = []
    if 't' in args.trim_sides.lower(): sides_display.append('top')
    if 'b' in args.trim_sides.lower(): sides_display.append('bottom')
    if 'l' in args.trim_sides.lower(): sides_display.append('left')
    if 'r' in args.trim_sides.lower(): sides_display.append('right')
    
    print("=" * 50)
    print("Composite Image Splitter")
    print("=" * 50)
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print(f"Format: {args.format.upper()} (quality: {args.quality})")
    print(f"Recursive: {'Yes' if args.recursive else 'No'}")
    if args.trim:
        print(f"Trim: {', '.join(sides_display)}")
    else:
        print(f"Trim: No")
    if suffix_list:
        print(f"Suffixes: {suffix_list}")
    else:
        print(f"Template: {args.suffix}")
    print("=" * 50 + "\n")
    
    if os.path.isfile(args.input):
        print(f"Processing: {args.input}")
        count = split_composite_image(args.input, args.output, **common_args)
        print(f"\nDone! Extracted {count} images -> {args.output}")
        
    elif os.path.isdir(args.input):
        total = process_directory(
            args.input, 
            args.output, 
            recursive=args.recursive,
            **common_args
        )
        print(f"\n{'='*50}")
        print(f"All done! Extracted {total} images -> {args.output}")
    else:
        print(f"Error: '{args.input}' not found")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())