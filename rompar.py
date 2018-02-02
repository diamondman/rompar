#! /usr/bin/env python

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
#

import cv2.cv as cv
import sys
import pickle
import traceback
import os

K_RIGHT = 65363
K_DOWN = 65362
K_LEFT = 65361
K_UP = 65364

import subprocess
def screen_wh():
    cmd = ['xrandr']
    cmd2 = ['grep', '*']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(cmd2, stdin=p.stdout, stdout=subprocess.PIPE)
    p.stdout.close()
     
    resolution_string, _junk = p2.communicate()
    resolution = resolution_string.split()[0]
    width, height = resolution.split('x')
    return int(width), int(height)

class View(object):
    def __init__(self):
        # Display objects
        # Crop / viewport
        self.x = 0
        self.y = 0
        screenw, screenh = screen_wh()
        # Displayed coordinates
        self.w = screenw - 100
        self.h = screenh - 100
        # Step increment
        self.incx = screenw // 3
        self.incy = screenh // 3

class Config(object):
    def __init__(self):
        # Display options
        # Overlay bit position grid
        self.img_display_grid = True
        # Show source image (ie without thresholding)
        self.img_display_original = False
        # Remove image entirely, showing just decoded bits
        self.img_display_blank_image = False
        # Show image only in bit ROI
        self.img_display_peephole = False
        # Overlay hex data on image
        self.img_display_data = False
        # Overlay binary data on image
        self.img_display_binary = False
        # Bit is 1 if sum of pixels in area > (max possible value / thresh_div)
        # ie 10 => set if average value at least 1/10 max brightness  
        # Feel this is sort of a weird way to do this
        self.bit_thresh_div = 10
        # Pixel value >= to consider occupied
        self.pix_thresh_min = 0xae
    
        # Image processing options
        self.dilate = 0
        self.erode = 0
        # Bit image radius as displayed on grid
        # Actual detection uses square around circle
        self.radius = 0
        # User supplied radius to be used in lieu of auto calculated
        self.default_radius = None
        self.threshold = True
    
        self.LSB_Mode = False
    
        self.font_size = None

        self.view = View()
        
        self.save_dat = False

class Rompar(object):
    def __init__(self):
        self.gui = True

        # Main state
        # Have we attempted to decode bits?
        self.data_read = False

        # Pixels between cols
        self.step_x = 0
        # Pixels between rows
        self.step_y = 0
        # Number of rows/cols per bit grouping
        self.group_cols = 0
        self.group_rows = 0

        self.Search_HEX = None
        # Number of save commands issued
        # Used to create unique save file postfix per save
        self.saven = 0

        # >= 0 when in edit mode
        self.Edit_x = -1
        self.Edit_y = -1

        # Processed data
        self.inverted = False
        self.Data = []
        # Global
        self.grid_points_x = []
        self.grid_points_y = []
        self.grid_intersections = []

        # Misc
        # Process events while true
        self.running = True

        # Image buffers
        self.img_target = None
        self.img_grid = None
        self.img_mask = None
        self.img_peephole = None
        self.img_display = None
        self.img_display_viewport = None
        self.img_blank = None
        self.img_hex = None
        # Font currently rendering
        self.font = None
    
        # Be more verbose
        # Crash on exceptions
        self.debug = False

        self.config = Config()

def get_pixel(self, x, y):
    return self.img_target[x, y][0] + self.img_target[x, y][1] + self.img_target[x, y][2]


# create binary printable string
def to_bin(x):
    return ''.join(x & (1 << i) and '1' or '0' for i in range(7, -1, -1))


def redraw_grid(self):
    if not self.gui:
        return
    cv.Set(self.img_grid, cv.Scalar(0, 0, 0))
    cv.Set(self.img_peephole, cv.Scalar(0, 0, 0))
    self.grid_intersections = []
    self.grid_points_x.sort()
    self.grid_points_y.sort()

    for x in self.grid_points_x:
        cv.Line(self.img_grid, (x, 0), (x, self.img_target.height), cv.Scalar(0xff, 0x00, 0x00),
                1)
        for y in self.grid_points_y:
            self.grid_intersections.append((x, y))
    self.grid_intersections.sort()
    for y in self.grid_points_y:
        cv.Line(self.img_grid, (0, y), (self.img_target.width, y), cv.Scalar(0xff, 0x00, 0x00),
                1)
    for x, y in self.grid_intersections:
        cv.Circle(
            self.img_grid, (x, y), self.config.radius, cv.Scalar(0x00, 0x00, 0x00), thickness=-1)
        cv.Circle(
            self.img_grid, (x, y), self.config.radius, cv.Scalar(0xff, 0x00, 0x00), thickness=1)
        cv.Circle(
            self.img_peephole, (x, y),
            self.config.radius + 1,
            cv.Scalar(0xff, 0xff, 0xff),
            thickness=-1)

def update_radius(self):
    if self.config.radius:
        return

    if self.config.default_radius:
        self.config.radius = self.config.default_radius
    else:
        if self.step_x:
            self.config.radius = int(self.step_x / 3)
        elif self.step_y:
            self.config.radius = int(self.step_y / 3)

def on_mouse_left(img_x, img_y, flags, param):
    self = param

    # Edit data
    if self.data_read:
        # find nearest intersection and toggle its value
        for x in self.grid_points_x:
            if img_x >= x - self.config.radius / 2 and img_x <= x + self.config.radius / 2:
                for y in self.grid_points_y:
                    if img_y >= y - self.config.radius / 2 and img_y <= y + self.config.radius / 2:
                        value = toggle_data(self, x, y)
                        #print self.img_target[x, y]
                        #print 'value', value
                        if value == '0':
                            cv.Circle(
                                self.img_grid, (x, y),
                                self.config.radius,
                                cv.Scalar(0xff, 0x00, 0x00),
                                thickness=2)
                        else:
                            cv.Circle(
                                self.img_grid, (x, y),
                                self.config.radius,
                                cv.Scalar(0x00, 0xff, 0x00),
                                thickness=2)

                        show_image(self)
    # Edit grid
    else:
        #if not Target[img_y, img_x]:
        if flags != cv.CV_EVENT_FLAG_SHIFTKEY and not get_pixel(self,
                img_y, img_x):
            print 'autocenter: miss!'
            return

        if img_x in self.grid_points_x:
            return
        # only draw a single line if this is the first one
        if len(self.grid_points_x) == 0 or self.group_cols == 1:
            if flags != cv.CV_EVENT_FLAG_SHIFTKEY:
                img_x, img_y = auto_center(self, img_x, img_y)

            # don't try to auto-center if shift key pressed
            draw_line(self, img_x, img_y, 'V', False)
            self.grid_points_x.append(img_x)
            if self.group_rows == 1:
                draw_line(self, img_x, img_y, 'V', True)
        else:
            # set up auto draw
            if len(self.grid_points_x) == 1:
                # use a float to reduce rounding errors
                self.step_x = float(img_x - self.grid_points_x[0]) / (self.group_cols - 1)
                # reset stored self.Data as main loop will add all entries
                img_x = self.grid_points_x[0]
                self.grid_points_x = []
                update_radius(self)
            # draw a full set of self.group_cols
            for x in range(self.group_cols):
                draw_x = int(img_x + x * self.step_x)
                self.grid_points_x.append(draw_x)
                draw_line(self, draw_x, img_y, 'V', True)

def on_mouse_right(img_x, img_y, flags, param):
    self = param

    # Edit data
    if self.data_read:
        # find row and select for editing
        for x in self.grid_points_x:
            for y in self.grid_points_y:
                if img_y >= y - self.config.radius / 2 and img_y <= y + self.config.radius / 2:
                    #print 'value', get_data(x,y)
                    # select the whole row
                    xcount = 0
                    for x in self.grid_points_x:
                        if img_x >= x - self.config.radius / 2 and img_x <= x + self.config.radius / 2:
                            self.Edit_x = xcount
                            break
                        else:
                            xcount += 1
                    # highlight the bit group we're in
                    sx = self.Edit_x - (self.Edit_x % self.group_cols)
                    self.Edit_y = y
                    read_data(self)
                    show_image(self)
                    return
    # Edit grid
    else:
        if flags != cv.CV_EVENT_FLAG_SHIFTKEY and not get_pixel(self,
                img_y, img_x):
            print 'autocenter: miss!'
            return
        if img_y in self.grid_points_y:
            return
        # only draw a single line if this is the first one
        if len(self.grid_points_y) == 0 or self.group_rows == 1:
            if flags != cv.CV_EVENT_FLAG_SHIFTKEY:
                img_x, img_y = auto_center(self, img_x, img_y)

            draw_line(self, img_x, img_y, 'H', False)
            self.grid_points_y.append(img_y)
            if self.group_rows == 1:
                draw_line(self, img_x, img_y, 'H', True)
        else:
            # set up auto draw
            if len(self.grid_points_y) == 1:
                # use a float to reduce rounding errors
                self.step_y = float(img_y - self.grid_points_y[0]) / (self.group_rows - 1)
                # reset stored self.Data as main loop will add all entries
                img_y = self.grid_points_y[0]
                self.grid_points_y = []
                update_radius(self)
            # draw a full set of self.group_rows
            for y in range(self.group_rows):
                draw_y = int(img_y + y * self.step_y)
                # only draw up to the edge of the image
                if draw_y > self.img_original.height:
                    break
                self.grid_points_y.append(draw_y)
                draw_line(self, img_x, draw_y, 'H', True)


# mouse events
def on_mouse(event, mouse_x, mouse_y, flags, param):
    img_x = mouse_x + self.config.view.x
    img_y = mouse_y + self.config.view.y

    # draw vertical grid lines
    if event == cv.CV_EVENT_LBUTTONDOWN:
        on_mouse_left(img_x, img_y, flags, param)
    # draw horizontal grid lines
    elif event == cv.CV_EVENT_RBUTTONDOWN:
        on_mouse_right(img_x, img_y, flags, param)


def show_image(self):
    if self.config.img_display_original:
        self.img_display = cv.CloneImage(self.img_original)
    else:
        self.img_display = cv.CloneImage(self.img_target)

    if self.config.img_display_blank_image:
        self.img_display = cv.CloneImage(self.img_blank)

    if self.config.img_display_grid:
        cv.Or(self.img_display, self.img_grid, self.img_display)

    if self.config.img_display_peephole:
        cv.And(self.img_display, self.img_peephole, self.img_display)

    if self.config.img_display_data:
        show_data(self)
        cv.Or(self.img_display, self.img_hex, self.img_display)

    self.img_display_viewport = self.img_display[self.config.view.y:self.config.view.y+self.config.view.h,
                                                 self.config.view.x:self.config.view.x+self.config.view.w]
    cv.ShowImage(self.title, self.img_display_viewport)

def auto_center(self, x, y):
    '''
    Auto center image global x/y coordinate on contiguous pixel x/y runs
    '''
    x_min = x
    while get_pixel(self, y, x_min) != 0.0:
        x_min -= 1
    x_max = x
    while get_pixel(self, y, x_max) != 0.0:
        x_max += 1
    x = x_min + ((x_max - x_min) / 2)
    y_min = y
    while get_pixel(self, y_min, x) != 0.0:
        y_min -= 1
    y_max = y
    while get_pixel(self, y_max, x) != 0.0:
        y_max += 1
    y = y_min + ((y_max - y_min) / 2)
    return x, y

# draw grid
def draw_line(self, x, y, direction, intersections):
    print 'draw_line', x, y, direction, intersections, len(self.grid_points_x), len(self.grid_points_y)

    if direction == 'H':
        print 'Draw H line', (0, y), (self.img_target.width, y)
        cv.Line(self.img_grid, (0, y), (self.img_target.width, y), cv.Scalar(0xff, 0x00, 0x00),
                1)
        for gridx in self.grid_points_x:
            print '*****self.grid_points_x circle', (gridx, y), self.config.radius
            cv.Circle(
                self.img_grid, (gridx, y),
                self.config.radius,
                cv.Scalar(0x00, 0x00, 0x00),
                thickness=-1)
            cv.Circle(self.img_grid, (gridx, y), self.config.radius, cv.Scalar(0xff, 0x00, 0x00))
            if intersections:
                self.grid_intersections.append((gridx, y))
    else:
        cv.Line(self.img_grid, (x, 0), (x, self.img_target.height), cv.Scalar(0xff, 0x00, 0x00),
                1)
        for gridy in self.grid_points_y:
            cv.Circle(
                self.img_grid, (x, gridy),
                self.config.radius,
                cv.Scalar(0x00, 0x00, 0x00),
                thickness=-1)
            cv.Circle(self.img_grid, (x, gridy), self.config.radius, cv.Scalar(0xff, 0x00, 0x00))
            if intersections:
                self.grid_intersections.append((x, gridy))
    show_image(self)
    print 'draw_line grid intersections:', len(self.grid_intersections)


def read_data(self, data_ref=None, force=False):
    if not force and not self.data_read:
        return

    redraw_grid(self)

    # maximum possible value if all pixels are set
    maxval = (self.config.radius * self.config.radius) * 255
    print 'read_data max aperture value:', maxval

    if data_ref:
        print 'read_data: loading reference data (%d entries)' % len(data_ref)
        print 'Grid intersections: %d' % len(self.grid_intersections)
        self.Data = data_ref
    else:
        print 'read_data: computing'
        # Compute
        self.Data = []
        for x, y in self.grid_intersections:
            value = 0
            # FIXME: misleading
            # This isn't a radius but rather a bounding box
            for xx in range(x - (self.config.radius / 2), x + (self.config.radius / 2)):
                for yy in range(y - (self.config.radius / 2), y + (self.config.radius / 2)):
                    value += get_pixel(self, yy, xx)
            if value > maxval / self.config.bit_thresh_div:
                self.Data.append('1')
            else:
                self.Data.append('0')

    # Render
    for i, (x, y) in enumerate(self.grid_intersections):
        if self.Data[i] == '1':
            cv.Circle(
                self.img_grid, (x, y), self.config.radius, cv.Scalar(0x00, 0xff, 0x00), thickness=2)
            # highlight if we're in edit mode
            if y == self.Edit_y:
                sx = self.Edit_x - (self.Edit_x % self.group_cols)
                if self.grid_points_x.index(x) >= sx and self.grid_points_x.index(
                        x) < sx + self.group_cols:
                    cv.Circle(
                        self.img_grid, (x, y),
                        self.config.radius,
                        cv.Scalar(0xff, 0xff, 0xff),
                        thickness=2)
        else:
            pass
    self.data_read = True


def show_data(self):
    if not self.data_read:
        return

    cv.Set(self.img_hex, cv.Scalar(0, 0, 0))
    print
    dat = get_all_data(self)
    for row in range(len(self.grid_points_y)):
        out = ''
        outbin = ''
        for column in range(len(self.grid_points_x) / self.group_cols):
            thisbyte = ord(dat[column * len(self.grid_points_y) + row])
            hexbyte = '%02X ' % thisbyte
            out += hexbyte
            outbin += to_bin(thisbyte) + ' '
            if self.config.img_display_binary:
                disp_data = to_bin(thisbyte)
            else:
                disp_data = hexbyte
            if self.config.img_display_data:
                if self.Search_HEX and self.Search_HEX.count(thisbyte):
                    cv.PutText(self.img_hex, disp_data,
                               (self.grid_points_x[column * self.group_cols],
                                self.grid_points_y[row] + self.config.radius / 2 + 1), self.font,
                               cv.Scalar(0x00, 0xff, 0xff))
                else:
                    cv.PutText(self.img_hex, disp_data,
                               (self.grid_points_x[column * self.group_cols],
                                self.grid_points_y[row] + self.config.radius / 2 + 1), self.font,
                               cv.Scalar(0xff, 0xff, 0xff))
        #print outbin
        #print
        #print out
    print


def get_all_data(self):
    '''Return data as bytes'''
    out = ''
    for column in range(len(self.grid_points_x) / self.group_cols):
        for row in range(len(self.grid_points_y)):
            thischunk = ''
            for x in range(self.group_cols):
                thisbit = self.Data[x * len(self.grid_points_y) + row +
                               column * self.group_cols * len(self.grid_points_y)]
                if self.inverted:
                    if thisbit == '0':
                        thisbit = '1'
                    else:
                        thisbit = '0'
                thischunk += thisbit
            for x in range(self.group_cols / 8):
                thisbyte = thischunk[x * 8:x * 8 + 8]
                # reverse self.group_cols if we want LSB
                if self.config.LSB_Mode:
                    thisbyte = thisbyte[::-1]
                out += chr(int(thisbyte, 2))
    return out

def data_as_xy(self):
    '''Return data as binary chars in ret[(x, y)] map'''
    ret = {}
    for d, (x, y) in zip(self.Data, self.grid_intersections):
        ret[(x, y)] = d
    return ret

def data_as_cr(self):
    '''Return data as binary chars in ret[(column, row)] map'''
    ret = {}
    xys = data_as_xy(self)
    for xi, x in enumerate(self.grid_points_x):
        for yi, y in enumerate(self.grid_points_y):
            ret[(xi, yi)] = xys[(x, y)]
    return ret

# call with exact values for intersection
def get_data(self, x, y):
    return self.Data[self.grid_intersections.index((x, y))]

def set_data(self, x, y, val):
    i = self.grid_intersections.index((x, y))
    self.Data[i] = val

def toggle_data(self, x, y):
    i = self.grid_intersections.index((x, y))
    if self.Data[i] == '0':
        self.Data[i] = '1'
    else:
        self.Data[i] = '0'
    return self.Data[i]

def cmd_find(self, k):
    print 'Enter space delimeted HEX (in image window), e.g. 10 A1 EF: ',
    sys.stdout.flush()
    shx = ''
    while 42:
        c = cv.WaitKey(0)
        # BS or DEL
        if c == 65288 or c == 65535 or k == 65439:
            c = 0x08
        if c > 255:
            continue

        # Newline
        if c == 0x0d or c == 0x0a:
            print
            break
        # Backspace
        elif c == 0x08:
            if not shx:
                sys.stdout.write('\a')
                sys.stdout.flush()
                continue
            sys.stdout.write('\b \b')
            sys.stdout.flush()
            shx = shx[:-1]
        else:
            c = chr(c)
            sys.stdout.write(c)
            sys.stdout.flush()
            shx += c
    try:
        self.Search_HEX = [int(h, 16) for h in shx.strip().split(' ')]
    except ValueError:
        print 'Invalid hex value'
        return
    print 'searching for', shx.upper()

def symlinka(target, alias):
    '''Atomic symlink'''
    tmp = alias + '_'
    if os.path.exists(tmp):
        os.unlink(tmp)
    os.symlink(target, alias + '_')
    os.rename(tmp, alias)

def save_grid(self, fn=None):
    if not fn:
        fn = self.basename + '_s%d.grid' % self.saven
    symlinka(fn, self.basename + '.grid')
    gridout = open(fn, 'wb')
    pickle.dump((self.grid_intersections, self.Data, self.grid_points_x, self.grid_points_y, self.config), gridout)
    print 'Saved %s' % fn

def load_grid(self, grid_file=None, apickle=None, gui=True):
    self.gui = gui
    if not apickle:
        with open(grid_file, 'rb') as gridfile:
            apickle = pickle.load(gridfile)
    self.grid_intersections, data, self.grid_points_x, self.grid_points_y, self.config = apickle

    # Possible only one direction is drawn
    if self.grid_intersections:
        # Some past DBs had corrupt sets with duplicates
        # Maybe better to just trust them though
        self.grid_points_x = []
        self.grid_points_y = []
        for x, y in self.grid_intersections:
            try:
                self.grid_points_x.index(x)
            except:
                self.grid_points_x.append(x)
    
            try:
                self.grid_points_y.index(y)
            except:
                self.grid_points_y.append(y)

    print 'Grid points: %d x, %d y' % (len(self.grid_points_x), len(self.grid_points_y))
    squared = len(self.grid_points_x) * len(self.grid_points_y)
    if len(self.grid_intersections) != squared:
        print self.grid_points_x
        print self.grid_points_y
        raise Exception("%d != %d" % (len(self.grid_intersections), squared))

    self.step_x = 0.0
    if len(self.grid_points_x) > 1:
        self.step_x = self.grid_points_x[1] - self.grid_points_x[0]
    self.step_y = 0.0
    if len(self.grid_points_y) > 1:
        self.step_y = self.grid_points_y[1] - self.grid_points_y[0]
    if not self.config.default_radius:
        if self.step_x:
            self.config.radius = self.step_x / 3
        else:
            self.config.radius = self.step_y / 3
    redraw_grid(self)

    if data:
        print 'Initializing data'
        if len(data) != len(self.grid_intersections):
            raise Exception("%d != %d" % (len(data), len(self.grid_intersections)))    
        read_data(self, data_ref=data, force=True)

# self.Data packed into column based bytes
def save_dat(self):
    out = get_all_data(self)
    columns = len(self.grid_points_x) / self.group_cols
    chunk = len(out) / columns
    for x in range(columns):
        fn = self.basename + '_s%d-%d.dat' % (self.saven, x)
        symlinka(fn, self.basename + '_%d.dat' % x)
        with open(fn, 'wb') as outfile:
            outfile.write(out[x * chunk:x * chunk + chunk])
            print '%s: %d bytes' % (fn, chunk)

def save_txt(self):
    '''Write text file like bits sown in GUI. Space between row/cols'''
    fn = self.basename + '_s%d.txt' % self.saven
    symlinka(fn, self.basename + '.txt')
    crs = data_as_cr(self)
    with open(fn, 'w') as f:
        for row in xrange(len(self.grid_points_y)):
            # Put a space between row gaps
            if row and row % self.group_rows == 0:
                f.write('\n')
            for col in xrange(len(self.grid_points_x)):
                if col and col % self.group_cols == 0:
                    f.write(' ')
                f.write(crs[(col, row)])
            # Newline afer every row
            f.write('\n')
    print 'Saved %s' % fn

def pan(self, x, y):
    #imgw = self.img_target.cols
    #imgh = self.img_target.rows
    #imgw, imgh, _channels = self.img_target.shape
    imgw, imgh = cv.GetSize(self.img_target)
    self.config.view.x = min(max(0, self.config.view.x + x), imgw - self.config.view.w)
    self.config.view.y = min(max(0, self.config.view.y + y), imgh - self.config.view.h)

def next_save(self):
    '''Look for next unused save slot by checking grid files'''
    while True:
        fn = self.basename + '_s%d.grid' % self.saven
        if not os.path.exists(fn):
            break
        self.saven += 1

def cmd_save(self):
    print 'saving...'

    next_save(self)
    save_grid(self)

    if not self.data_read:
        print 'No bits to save'
    else:
        if 0 and self.save_dat:
            save_dat(self)
        save_txt(self)

def print_config(self):
    print 'Display'
    print '  Grid      %s' % self.config.img_display_grid
    print '  Original  %s' % self.config.img_display_original
    print '  Peephole  %s' % self.config.img_display_peephole
    print '  Data      %s' % self.config.img_display_data
    print '    As binary %s' % self.config.img_display_binary
    print 'Pixel processing'
    print '  Bit threshold divisor   %s' % self.config.bit_thresh_div
    print '  Pixel threshold minimum %s (0x%02X)' % (self.config.pix_thresh_min, self.config.pix_thresh_min)
    print '  Dilate    %s' % self.config.dilate
    print '  Erode     %s' % self.config.erode
    print '  Radius    %s' % self.config.radius
    print '  Threshold %s' % self.config.threshold
    print '  Step'
    print '    X       % 5.1f' % self.step_x
    print '    X       % 5.1f' % self.step_y
    print 'Bit state'
    print '  Data read %d' % self.data_read
    print '  Bits per group'
    print '    X       %d cols' % self.group_cols
    print '    Y       %d rows' % self.group_rows
    print '  Bit points total'
    print '    X       %d cols' % len(self.grid_points_x)
    print '    Y       %d rows' % len(self.grid_points_y)
    print '  Inverted  %d' % self.inverted
    print '  Intersections %d' % len(self.grid_intersections)
    print '  Viewport'
    print '    X       %d' % self.config.view.x
    print '    Y       %d' % self.config.view.y
    print '    W       %d' % self.config.view.w
    print '    H       %d' % self.config.view.h
    print '    PanX    %d' % self.config.view.incx
    print '    PanY    %d' % self.config.view.incy

def cmd_help():
    print 'a/A  decrease/increase radius of read aperture'
    print 'b    blank image (to view template)'
    print 'c    print status (ie configuration)'
    print 'd/D  decrease/increase dilation'
    print 'e/E  decrease/increase erosion'
    print 'f/F  decrease font size'
    print 'g    toggle grid display'
    print 'h    print help'
    print 'H    toggle binary / hex data display'
    print 'i    toggle invert data 0/1'
    print 'l    toggle LSB data order (default MSB)'
    print 'm/M  decrease/increase bit threshold divisor'
    print 'o    toggle original image display'
    print 'p    toggle peephole view'
    print 'q    quit'
    print 'r    read cols (end enter bit/grid editing mode)'
    print 'R    reset cols (and exit bit/grid editing mode)'
    print 's    show data values (HEX)'
    print 'S    save data and grid'
    print 't    apply threshold filter'
    print '-/+  decrease/increase threshold filter minimum'
    print '/    search for HEX (highlight when HEX shown)'
    print '?    print help'
    print

def cmd_help2():
    print 'to create template:'
    print
    print '  (note SHIFT will disable auto-centering)'
    print
    print '  columns:'
    print
    print '    left click on first bit in any row of any group'
    print '    left click on last bit in any row of that group'
    print '    left click on first bit in any row of each subsequent group'
    print
    print '  rows:'
    print
    print '    right click on any bit in first row of any group'
    print '    right click on any bit in last row of that group'
    print '    right click on any bit in each subsequent group'
    print
    print 'data/grid manipulation (after read command issued):'
    print
    print '  left click on any bit to toggle value'
    print '  right click to select row'
    print
    print '  in manipulation mode:'
    print
    print '  left-arrow to move entire column left'
    print '  right-arrow to move entire column right'
    print '  up-arrow to move entire row up'
    print '  down-arrow to move entire row down'
    print '  DEL to delete row'
    print '  BS to delete column'
    print

def on_key(self, k):
    if k == 65288 and self.Edit_x >= 0:
        # BS
        print 'deleting column'
        self.grid_points_x.remove(self.grid_points_x[self.Edit_x])
        self.Edit_x = -1
        read_data(self)
    elif k == K_LEFT:
        pan(self, -self.config.view.incx, 0)
    elif k == K_RIGHT:
        pan(self, self.config.view.incx, 0)
    elif k == K_UP:
        pan(self, 0, -self.config.view.incy)
    elif k == K_DOWN:
        pan(self, 0, self.config.view.incy)
        '''
    elif k == K_UP and self.Edit_y >= 0:
        # up arrow
        print 'editing line', self.Edit_y
        self.grid_points_y[self.grid_points_y.index(self.Edit_y)] -= 1
        self.Edit_y -= 1
        read_data(self)
    elif k == K_DOWN and self.Edit_y >= 0:
        # down arrow
        print 'editing line', self.Edit_y
        self.grid_points_y[self.grid_points_y.index(self.Edit_y)] += 1
        self.Edit_y += 1
        read_data(self)
    elif k == K_RIGHT and self.Edit_x >= 0:
        # right arrow - edit entrie column group
        print 'editing column', self.Edit_x
        sx = self.Edit_x - (self.Edit_x % self.group_cols)
        for x in range(sx, sx + self.group_cols):
            self.grid_points_x[x] += 1
        read_data(self)
    elif k == K_LEFT and self.Edit_x >= 0:
        # left arrow
        print 'editing column', self.Edit_x
        sx = self.Edit_x - (self.Edit_x % self.group_cols)
        for x in range(sx, sx + self.group_cols):
            self.grid_points_x[x] -= 1
        read_data(self)
        '''
    elif k == 65432 and self.Edit_x >= 0:
        # right arrow on numpad - edit single column
        print 'editing column', self.Edit_x
        self.grid_points_x[self.Edit_x] += 1
        read_data(self)
    elif k == 65430 and self.Edit_x >= 0:
        # left arrow on numpad - edit single column
        print 'editing column', self.Edit_x
        self.grid_points_x[self.Edit_x] -= 1
        read_data(self)
    elif (k == 65439 or k == 65535) and self.Edit_y >= 0:
        # delete
        print 'deleting row', self.Edit_y
        self.grid_points_y.remove(self.Edit_y)
        self.Edit_y = -1
        read_data(self)
    elif k == chr(10):
        # enter
        self.Edit_x = -1
        self.Edit_y = -1
        print 'Done editing'
        read_data(self)
    elif k == 'a':
        if self.config.radius:
            self.config.radius -= 1
            read_data(self)
        print 'Radius: %d' % self.config.radius
    elif k == 'A':
        self.config.radius += 1
        read_data(self)
        print 'Radius: %d' % self.config.radius
    elif k == 'b':
        self.config.img_display_blank_image = not self.config.img_display_blank_image
    elif k == 'c':
        print_config(self)
    elif k == 'd':
        self.config.dilate = max(self.config.dilate - 1, 0)
        print 'Dilate: %d' % self.config.dilate
        read_data(self)
    elif k == 'D':
        self.config.dilate += 1
        print 'Dilate: %d' % self.config.dilate
        read_data(self)
    elif k == 'e':
        self.config.erode = max(self.config.erode - 1, 0)
        print 'Erode: %d' % self.config.erode
        read_data(self)
    elif k == 'E':
        self.config.erode += 1
        print 'Erode: %d' % self.config.erode
        read_data(self)
    elif k == 'f':
        if self.config.font_size > 0.1:
            self.config.font_size -= 0.1
            self.font = cv.InitFont(
                cv.CV_FONT_HERSHEY_SIMPLEX,
                hscale=self.config.font_size,
                vscale=1.0,
                shear=0,
                thickness=1,
                lineType=8)
        print 'Font size: %d' % self.config.font_size
    elif k == 'F':
        self.config.font_size += 0.1
        self.font = cv.InitFont(
            cv.CV_FONT_HERSHEY_SIMPLEX,
            hscale=self.config.font_size,
            vscale=1.0,
            shear=0,
            thickness=1,
            lineType=8)
        print 'Font size: %d' % self.config.font_size
    elif k == 'g':
        self.config.img_display_grid = not self.config.img_display_grid
        print 'Display grid:', self.config.img_display_grid
    elif k == 'h' or k == '?':
        cmd_help()
    elif k == 'H':
        self.config.img_display_binary = not self.config.img_display_binary
        print 'Display binary:', self.config.img_display_binary
    elif k == 'i':
        self.inverted = not self.inverted
        print 'Inverted:', self.inverted
    elif k == 'l':
        self.config.LSB_Mode = not self.config.LSB_Mode
        print 'LSB self.Data mode:', self.config.LSB_Mode
    elif k == 'm':
        self.config.bit_thresh_div -= 1
        print 'thresh_div:', self.config.bit_thresh_div
        read_data(self)
    elif k == 'M':
        self.config.bit_thresh_div += 1
        print 'thresh_div:', self.config.bit_thresh_div
        read_data(self)
    elif k == 'o':
        self.config.img_display_original = not self.config.img_display_original
        print 'display original:', self.config.img_display_original
    elif k == 'p':
        self.config.img_display_peephole = not self.config.img_display_peephole
        print 'display peephole:', self.config.img_display_peephole
    elif k == 'r':
        print 'reading %d points...' % len(self.grid_intersections)
        read_data(self, force=True)
    elif k == 'R':
        redraw_grid(self)
        self.data_read = False
    elif k == 's':
        self.config.img_display_data = not self.config.img_display_data
        print 'show data:', self.config.img_display_data
    elif k == 'S':
        cmd_save(self)
    elif k == 'q':
        print "Exiting on q"
        self.running = False
    elif k == 't':
        self.config.threshold = True
        print 'Threshold:', self.config.threshold
    elif k == '-':
        self.config.pix_thresh_min = max(self.config.pix_thresh_min - 1, 0x01)
        print 'Threshold filter %02x' % self.config.pix_thresh_min
        if self.data_read:
            read_data(self)
    elif k == '+':
        self.config.pix_thresh_min = min(self.config.pix_thresh_min + 1, 0xFF)
        print 'Threshold filter %02x' % self.config.pix_thresh_min
        if self.data_read:
            read_data(self)
    elif k == '/':
        cmd_find(self, k)
    #else:
    #    print 'Unknown command %s' % k

def do_loop(self):
    # image processing
    if self.config.threshold:
        cv.Threshold(self.img_original, self.img_target, self.config.pix_thresh_min, 0xff, cv.CV_THRESH_BINARY)
        cv.And(self.img_target, self.img_mask, self.img_target)
    if self.config.dilate:
        cv.Dilate(self.img_target, self.img_target, iterations=self.config.dilate)
    if self.config.erode:
        cv.Erode(self.img_target, self.img_target, iterations=self.config.erode)
    show_image(self)

    sys.stdout.write('> ')
    sys.stdout.flush()
    # keystroke processing
    ki = cv.WaitKey(0)

    # Simple character value, if applicable
    kc = None
    # Char if a common char, otherwise the integer code
    k = ki

    if 0 <= ki < 256:
        kc = chr(ki)
        k = kc
    elif 65506 < ki < 66000 and ki != 65535:
        ki2 = ki - 65506 - 30
        # modifier keys
        if ki2 >= 0:
            kc = chr(ki2)
            k = kc

    if kc:
        print '%d (%s)\n' % (ki, kc)
    else:
        print '%d\n' % ki

    if ki > 66000:
        return
    if ki < 0:
        print "Exiting on closed window"
        self.running = False
        return
    on_key(self, k)

def run(self, image_fn, grid_file):

    #self.img_original= cv.LoadImage(image_fn, iscolor=cv.CV_LOAD_IMAGE_GRAYSCALE)
    #self.img_original= cv.LoadImage(image_fn, iscolor=cv.CV_LOAD_IMAGE_COLOR)
    self.img_original = cv.LoadImage(image_fn)
    print 'Image is %dx%d' % (self.img_original.width, self.img_original.height)

    self.basename = image_fn[:image_fn.find('.')]

    # image buffers
    self.img_target = cv.CreateImage(cv.GetSize(self.img_original), cv.IPL_DEPTH_8U, 3)
    self.img_grid = cv.CreateImage(cv.GetSize(self.img_original), cv.IPL_DEPTH_8U, 3)
    self.img_mask = cv.CreateImage(cv.GetSize(self.img_original), cv.IPL_DEPTH_8U, 3)
    self.img_peephole = cv.CreateImage(cv.GetSize(self.img_original), cv.IPL_DEPTH_8U, 3)
    cv.Set(self.img_mask, cv.Scalar(0x00, 0x00, 0xff))
    self.img_display = cv.CreateImage(cv.GetSize(self.img_original), cv.IPL_DEPTH_8U, 3)
    cv.Set(self.img_grid, cv.Scalar(0, 0, 0))
    self.img_blank = cv.CreateImage(cv.GetSize(self.img_original), cv.IPL_DEPTH_8U, 3)
    cv.Set(self.img_blank, cv.Scalar(0, 0, 0))
    self.img_hex = cv.CreateImage(cv.GetSize(self.img_original), cv.IPL_DEPTH_8U, 3)
    cv.Set(self.img_hex, cv.Scalar(0, 0, 0))

    self.config.font_size = 1.0
    self.font = cv.InitFont(
        cv.CV_FONT_HERSHEY_SIMPLEX,
        hscale=self.config.font_size,
        vscale=1.0,
        shear=0,
        thickness=1,
        lineType=8)

    self.title = "rompar %s" % image_fn
    cv.NamedWindow(self.title, 1)
    cv.SetMouseCallback(self.title, on_mouse, self)

    self.img_target = cv.CloneImage(self.img_original)

    if grid_file:
        load_grid(self, grid_file)

    cmd_help()
    cmd_help2()

    # main loop
    while self.running:
        try:
            do_loop(self)
        except Exception:
            if self.debug:
                raise
            print 'WARNING: exception'
            traceback.print_exc()

    print 'Exiting'

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Extract mask ROM image')
    parser.add_argument('--radius', type=int, help='Use given radius for display, bounded square for detection')
    parser.add_argument('--bit-thresh-div', type=str, help='Bit set area threshold divisor')
    # Only care about min
    parser.add_argument('--pix-thresh', type=str, help='Pixel is set threshold minimum')
    parser.add_argument('--dilate', type=str, help='Dilation')
    parser.add_argument('--erode', type=str, help='Erosion')
    parser.add_argument('--debug', action='store_true', help='')
    parser.add_argument('image', help='Input image')
    parser.add_argument('cols_per_group', type=int, help='')
    parser.add_argument('rows_per_group', type=int, help='')
    parser.add_argument('grid_file', nargs='?', help='Load saved grid file')
    args = parser.parse_args()

    self = Rompar()
    self.debug = args.debug
    self.group_cols = args.cols_per_group
    self.group_rows = args.rows_per_group
    if args.radius:
        self.config.default_radius = args.radius
        self.config.radius = args.radius
    if args.bit_thresh_div:
        self.config.bit_thresh_div = int(args.bit_thresh_div, 0)
    if args.pix_thresh:
        self.config.pix_thresh_min = int(args.pix_thresh, 0)
    if args.dilate:
        self.config.dilate = int(args.dilate, 0)
    if args.erode:
        self.config.erode = int(args.erode, 0)

    run(self, args.image, grid_file=args.grid_file)
