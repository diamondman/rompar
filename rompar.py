#! /usr/bin/env python

# Modifications by John McMaster <JohnDMcMaster@gmail.com>
# Original copyright below
#
#  rompar.py - semi-auto read masked rom
#
#  Adam Laurie <adam@aperturelabs.com>
#  http://www.aperturelabs.com
#
#  This code is copyright (c) Aperture Labs Ltd., 2013, All rights reserved.
#
#    This code is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This code is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

from rompar import Rompar, RomparUIOpenCV, Config

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Extract mask ROM image')
    parser.add_argument('--radius', type=int,
                        help='Use given radius for display, '
                        'bounded square for detection')
    parser.add_argument('--bit-thresh-div', type=str,
                        help='Bit set area threshold divisor')
    # Only care about min
    parser.add_argument('--pix-thresh', type=str,
                        help='Pixel is set threshold minimum')
    parser.add_argument('--dilate', type=str, help='Dilation')
    parser.add_argument('--erode', type=str, help='Erosion')
    parser.add_argument('--debug', action='store_true', help='')
    parser.add_argument('--load', help='Load saved grid file')
    parser.add_argument('image', nargs='?', help='Input image')
    parser.add_argument('cols_per_group', nargs='?', type=int, help='')
    parser.add_argument('rows_per_group', nargs='?', type=int, help='')
    args = parser.parse_args()

    config = Config()
    if args.radius:
        config.default_radius = args.radius
        config.radius = args.radius
    if args.bit_thresh_div:
        config.bit_thresh_div = int(args.bit_thresh_div, 0)
    if args.pix_thresh:
        config.pix_thresh_min = int(args.pix_thresh, 0)
    if args.dilate:
        config.dilate = int(args.dilate, 0)
    if args.erode:
        config.erode = int(args.erode, 0)

    romp = Rompar(config,
                  img_fn=args.image, grid_file=args.load,
                  group_cols=args.cols_per_group,
                  group_rows=args.rows_per_group)

    rompUI = RomparUIOpenCV(romp, debug=args.debug)
    rompUI.run()

if __name__ == "__main__":
    main()
