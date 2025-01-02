#!/usr/bin/env python

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

# Controls verbosity of subcommands
__verbose__ = False

# Catches pipeline errors from helper functions
class PipelineError(Exception):
    """Exception raised when helper functions encounter an error"""
    pass

# Uses subprocess.run to run a command, and prints the command and output if verbose is set
#
# Example:
#   result = run_command(['c3d', my_image, '-swapdim', output_orientation, '-o', reoriented_image])
#
# Input: a list of command line arguments
#
# Returns a dictionary with keys 'cmd_str', 'stderr', 'stdout'
#
# Raises PipelineError if the command returns a non-zero exit code
#
def run_command(cmd):
    # Just to be clear we use the global var set by the main function
    global __verbose__

    if (__verbose__):
        print(f"--- Running {cmd[0]} ---")
        print(" ".join(cmd))

    result = subprocess.run(cmd, check = False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if (__verbose__):
        print("--- command stdout ---")
        print(result.stdout)
        print("--- command stderr ---")
        print(result.stderr)
        print(f"--- end {cmd[0]} ---")

    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}")
        traceback.print_stack()
        if not __verbose__: # print output if not already printed
            print('command stdout:\n' + result.stdout)
            print('command stderr:\n' + result.stderr)
            raise PipelineError(f"Error running command: {' '.join(cmd)}")

    return { 'cmd_str': ' '.join(cmd), 'stderr': result.stderr, 'stdout': result.stdout }


# Trim the neck from the image, and pad with empty space on all sides.
# Resample the mask into the trimmed space
# Return trimmed images plus a mask in the original space containing the trim region
# and brain mask for QC
#
# Inputs:
#   input_image - the input T1w image to this should be the output from run_hdbet (already reoriented to LPI)
#   working_dir - the working directory
#   pad_mm - number of mm to pad on each side after trimming
#
def trim_neck(input_image, working_dir, pad_mm=10):

    # Conform input to orientation and write to temp dir
    reoriented_image = os.path.join(working_dir, f"input_reoriented_LPI.nii.gz")

    result = run_command(['c3d', input_image, '-swapdim', 'LPI', '-o', reoriented_image])

    # trim neck with c3d, reslice mask into trimmed space
    tmp_image_trim = os.path.join(working_dir, 'T1wNeckTrim.nii.gz')
    tmp_mask_trim = os.path.join(working_dir, 'T1wNeckTrim_mask.nii.gz')

    # This is in the original space, and contains 1 for voxels in the trimmed output
    # and 0 for voxels outside the trimmed region. Used for QC
    tmp_trim_region_image = os.path.join(working_dir, 'T1wNeckTrim_region.nii.gz')

    result = run_command(['trim_neck.sh', '-c', '20', '-w', working_dir, reoriented_image, tmp_image_trim])

    # Pad image with c3d and reslice mask to same space
    result = run_command(['c3d', tmp_image_trim, '-pad', f"{pad_mm}x{pad_mm}x{pad_mm}mm",
                            f"{pad_mm}x{pad_mm}x{pad_mm}mm", '0', '-o', tmp_image_trim])

    return tmp_image_trim


# Helps with CLI help formatting
class RawDefaultsHelpFormatter(
    argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter
):
    pass


def main():

    global __verbose__

    parser = argparse.ArgumentParser(formatter_class=RawDefaultsHelpFormatter,
                                    add_help = False,
                                    description='''Neck trim an anatomical image and conform to LPI orientation with c3d.

    ''')
    required = parser.add_argument_group('Required arguments')
    required.add_argument("--input", help="Input image", type=str,
                          required=True)
    required.add_argument("--output", help="Output image", type=str, required=True)
    optional = parser.add_argument_group('Optional arguments')
    optional.add_argument("-h", "--help", action="help", help="show this help message and exit")
    args = parser.parse_args()

    # Check we have c3d and trim_neck.sh in the path
    try:
        result = run_command(['c3d', '-h'])
    except PipelineError:
        print("Could not run c3d, check PATH")
        sys.exit(1)

    try:
        result = run_command(['trim_neck.sh', '-h'])
    except PipelineError:
        print("Could not run trim_neck.sh, check PATH")
        sys.exit(1)

    # Make this under system TMPDIR, cleaned up automatically
    base_working_dir_tmpdir = tempfile.TemporaryDirectory(suffix='t1wpreproc.tmpdir')
    base_working_dir = base_working_dir_tmpdir.name

    if not os.path.exists(args.input):
        print(f"Input image {args.input} does not exist")
        sys.exit(1)

    output_dir = os.path.dirname(args.output)

    if len(output_dir) > 0 and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    trimmed = trim_neck(args.input, base_working_dir, pad_mm=10)

    shutil.copyfile(trimmed, args.output)

if __name__ == "__main__":
    main()