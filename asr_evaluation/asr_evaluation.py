from __future__ import division

import editdistance
import sys
import argparse
from itertools import izip
from collections import defaultdict

# This is the command line interface!
parser = argparse.ArgumentParser(description='Evaluate an ASR transcript against a reference transcript.')
parser.add_argument('ref', type=file, help='the reference transcript filename')
parser.add_argument('hyp', type=file, help='the ASR hypothesis filename')
parser.add_argument('-i', '--print-instances', action='store_true', help='print the individual sentences and their errors')
parser.add_argument('-id', '--has-ids', action='store_true', help='hypothesis and reference files have ids in the last token?')
parser.add_argument('-c', '--confusions', action='store_true', help='print tables of which words were confused')
parser.add_argument('-p', '--print-wer-vs-length', action='store_true', help='print table of average WER grouped by reference sentence length')
parser.add_argument('-m', '--min-word-count', type=int, default=10, metavar='count', help='minimum word count to show a word in confusions')
args = parser.parse_args()

# Put the command line options into global variables.
print_instances = args.print_instances
files_have_ids = args.has_ids
confusions = args.confusions
min_count= args.min_word_count
plot= args.print_wer_vs_length

# For keeping track of the total number of tokens, errors, and matches
ref_token_count = 0
error_count = 0
match_count = 0

# For keeping track of word error rates by sentence length
# this is so we can see if performance is better/worse for longer
# and/or shorter sentences
lengths = []
error_rates = []
wer_bins = [[] for x in xrange(20)]

# Tables for keeping track of which words get confused with one another
insertion_table = defaultdict(int)
deletion_table = defaultdict(int)
substitution_table = defaultdict(int)

# These are the editdistance opcodes that are condsidered 'errors'
error_codes = ['replace', 'delete', 'insert']

def main():
    """Main method - this reads the hyp and ref files, and creates
    editdistance.SequenceMatcher objects to compute the edit distance.
    All the statistics necessary statistics are collected, and results are
    printed as specified by the command line options.

    This function doesn't not check to ensure that the reference and
    hypothesis file have the same number of lines.  It will stop after the
    shortest one runs out of lines.  This should be easy to fix...
    """
    global error_count
    global match_count
    global ref_token_count
    counter = 1
    # Loop through each line of the reference and hyp file
    for ref_line, hyp_line in izip(args.ref, args.hyp):
        ref = ref_line.split()
        hyp = hyp_line.split()
        id = None
        # If the files have IDs, then split the ID off from the text
        if files_have_ids:
            ref_id = ref[-1]
            hyp_id = hyp[-1]
            assert (ref_id == hyp_id)
            id = ref_id
            ref = ref[:-1]
            hyp = hyp[:-1]
        # Create an object to get the edit distance, and then retrieve the
        # relevant counts that we need.
        sm = editdistance.SequenceMatcher(a=ref, b=hyp)
        errors = get_error_count(sm)
        matches = get_match_count(sm)
        ref_length = len(ref)
        # Increment the total counts we're tracking
        error_count += errors
        match_count += matches
        ref_token_count += ref_length
        # If we're keeping track of which words get mixed up with which others,
        # call track_confusions
        if confusions:
            track_confusions(sm, ref, hyp)
        # If we're printing instances, do it here (in roughly the align.c format)
        if print_instances:
            print_diff(sm, ref, hyp)
            if id:
                print "SENTENCE %d  %s"%(counter, id)
            else:
                print "SENTENCE %d"%counter
            print "Correct          = %5.1f%%  %3d   (%6d)" % (100.0 * matches / ref_length, matches, match_count)
            print "Errors           = %5.1f%%  %3d   (%6d)" % (100.0 * errors / ref_length, errors, error_count)
        # Keep track of the individual error rates, and reference lengths, so we
        # can compute average WERs by sentence length
        lengths.append(ref_length)
        error_rates.append(errors * 1.0 / len(ref))
        wer_bins[len(ref)].append(errors * 1.0 / len(ref))
        counter = counter + 1
    if confusions:
        print_confusions()
    print_wer_vs_length()
    print "WRR: %f %% (%10d / %10d)"%(100*match_count/ref_token_count, match_count, ref_token_count)
    print "WER: %f %% (%10d / %10d)"%(100*error_count/ref_token_count, error_count, ref_token_count)


def print_confusions ():
    """Print the confused words that we found... grouped by insertions, deletions
    and substitutions."""
    if len(insertion_table) > 0:
        print "INSERTIONS:"
        for item in sorted(insertion_table.items(), key=lambda x: x[1], reverse=True):
            if item[1] > min_count:
                print "%20s %10d"%item
    if len(deletion_table) > 0:
        print "DELETIONS:"
        for item in sorted(deletion_table.items(), key=lambda x: x[1], reverse=True):
            if item[1] > min_count:
                print "%20s %10d"%item    
    if len(substitution_table) > 0:
        print "SUBSTITUTIONS:"
        for [w1, w2], count in sorted(substitution_table.items(), key=lambda x: x[1], reverse=True):
            if count > min_count:
                print "%20s -> %20s   %10d"%(w1, w2, count)

def track_confusions(sm, seq1, seq2):
    """Keep track of the errors in a global variable, given a sequence matcher."""
    opcodes = sm.get_opcodes()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'insert':
            for i in range(j1,j2):
                word = seq2[i]
                insertion_table[word] += 1
        elif tag == 'delete':
            for i in range(i1,i2):
                word = seq1[i]
                deletion_table[word] += 1
        elif tag == 'replace':
            for w1 in seq1[i1:i2]:
                for w2 in seq2[j1:j2]:
                    key = (w1, w2)
                    substitution_table[key] += 1

# For some reason I'm getting two different counts depending on how I count the matches....
def get_match_count(sm):
    "Return the number of matches, given a sequence matcher object."
    matches = None
    matches1 = sm.matches()
    matching_blocks = sm.get_matching_blocks()
    matches2 = reduce(lambda x, y: x + y, map(lambda x: x[2], matching_blocks), 0)
    assert(matches1 == matches2)
    matches = matches1
    return matches

def get_error_count(sm):
    """Return the number of errors (insertion, deletion, and substitutiions
    , given a sequence matcher object."""
    opcodes = sm.get_opcodes()
    errors = filter(lambda x: x[0] in error_codes, opcodes)
    error_lengths = map(lambda x: max (x[2] - x[1], x[4] - x[3]), errors)
    return reduce(lambda x, y: x + y, error_lengths, 0)
    
def print_diff(sm, seq1, seq2):
    """Given a sequence matcher and the two sequences, print a Sphinx-style
    'diff' off the two."""
    ref_tokens = []
    hyp_tokens = []
    opcodes = sm.get_opcodes()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            for i in range(i1,i2):
                ref_tokens.append(seq1[i].lower())
            for i in range(j1,j2):
                hyp_tokens.append(seq2[i].lower())
        elif tag == 'delete':
            for i in range(i1,i2):
                ref_tokens.append(seq1[i].upper())
            for i in range(i1,i2):
                hyp_tokens.append('*' * len(seq1[i]))
        elif tag == 'insert':
            for i in range(j1,j2):
                ref_tokens.append('*' * len(seq2[i]))
            for i in range(j1,j2):
                hyp_tokens.append(seq2[i].upper())
        elif tag == 'replace':
            seq1_len = i2 - i1
            seq2_len = j2 - j1
            s1 = map(str.upper, seq1[i1:i2])
            s2 = map(str.upper, seq2[j1:j2])
            if seq1_len > seq2_len:
                for i in range(0, seq1_len-seq2_len):
                    s2.append(False)
            if seq1_len < seq2_len:
                for i in range(0, seq2_len-seq1_len):
                    s1.append(False)
            assert(len(s1) == len(s2))
            for i in range(0,len(s1)):
                w1 = s1[i]
                w2 = s2[i]
                # If we have two words, make them the same length
                if w1 and w2:
                    if len(w1) > len(w2):
                        s2[i] = w2 + ' '*(len(w1) - len(w2))
                    elif len(w1) < len(w2):
                        s1[i] = w1 + ' '*(len(w2) - len(w1))
                # Otherwise, create an empty word of the right width
                if w1 == False:
                    s1[i] = '*'*len(w2)
                if w2 == False:
                    s2[i] = '*'*len(w1)
            ref_tokens += s1
            hyp_tokens += s2

    print '='*60
    print "REF: %s"%' '.join(ref_tokens)
    print "HYP: %s"%' '.join(hyp_tokens)

def mean(seq):
    """Return the average of the elements of a sequence."""
    return float(sum(seq))/len(seq) if len(seq) > 0 else float('nan')
    
def print_wer_vs_length():
    """Print the average word error rate for each length sentence."""
    avg_wers = map(mean, wer_bins)
    for i in range(len(avg_wers)):
        print "%5d %f"%(i, avg_wers[i])
    print ""

    
# import matplotlib
# #import pylab
# from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
# from matplotlib.figure import Figure
# import matplotlib.mlab as mlab
# import numpy

# def plot_wers():
#     """Plotting the results in this way is not helpful.
#     however there are probably other useful plots we
#     could use."""
#     # Create a figure with size 6 x 6 inches.
#     fig = Figure(figsize=(6,6))
#     # Create a canvas and add the figure to it.
#     canvas = FigureCanvas(fig)
#     # Create a subplot.
#     ax = fig.add_subplot(111)
#     # Set the title.
#     ax.set_title("WER vs sentence length",fontsize=14)
#     # Set the X Axis label.
#     ax.set_xlabel("sentence length (# of words)",fontsize=12)    
#     # Set the Y Axis label.
#     ax.set_ylabel("WER", fontsize=12)
#     # Display Grid.
#     #ax.grid(True,linestyle='-',color='0.75')    
#     # Generate the Scatter Plot.
#     #ax.scatter(lengths, error_rates, s=20,color='tomato');    
#     ax.scatter(lengths, error_rates, color='tomato');    
#     # Save the generated Scatter Plot to a PNG file.
#     canvas.print_figure('wer-vs-length.png',dpi=500)



if __name__ == "__main__":
    main()
