import ast, random, os, sys
from collections import Counter

import string, csv
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

from scipy.spatial.distance import cosine

# GET METADATA

# Because a volume can have more than one genre, the metadata for this
# experiment is not a table of rows uniquely identified by docid.

# Instead, each row records an *assignment* of a docid to a genre,
# and there can be multiple rows for a single volume/docid.

# We also have "date" recorded in each row, because we are often going
# to want to select volumes from a subset of a category limited by date.
# We could build pandas dataframes to do that, but it seems simpler just
# to use a numpy mask

# We'll create a dictionary genreframes that has a separate key for each genre;
# the value for each genre will be a pandas dataframe. We can easily limit this
# by date.

genredocs = dict()
genredates = dict()
genreauthors = dict()
allgenres = ['allnonrandom']

genredocs['allnonrandom'] = list()
genredates['allnonrandom'] = list()
genreauthors['allnonrandom'] = list()

# LOAD vectors

vectors = dict()

# The first column is docid, the rest are floats
# for a particular word, scaled by idf.

with open('delta_matrix_loc2.tsv', encoding = 'utf-8') as f:
    for line in f:
        fields = line.strip().split('\t')
        if fields[0] == 'docid':
            continue   # that's the header
        thevector = np.array([float(x) for x in fields[1:]])
        docid = fields[0]
        vectors[docid] = thevector

# Now, the question is, how should we sample volumes? Many volumes
# may be in more than one category. If we test in-genre distance for
# every category they're a member of, volumes with multiple assignments
# may be overrepresented.

# So we are instead going to sample from a list of volumes,
# and then secondarily select from within the list of non-random
# genres for that volume. To do that we'll create the following dictionary:

weirdvols = pd.read_csv('taggedparts/all2remove.tsv', sep = '\t')
weirdvols = set(weirdvols.loc[weirdvols.remove != 'n', 'docid'])
print(len(weirdvols))

all_genre_assigns = dict()

with open('filtered_meta_4loc2.tsv', encoding = 'utf-8') as f:
    reader = csv.DictReader(f, delimiter = '\t')
    for row in reader:
        r = row['remove']
        if len(r) > 1:
            print(r)
            continue

        docid = row['docid']
        if docid in weirdvols:
            continue

        if docid not in vectors:
            docid = docid.replace('.$b', '.b')
            if docid not in vectors:
                print('skip')
                continue

        genrestring = row['exp_genres']
        genreset = genrestring.split('|')
        for g in genreset:
            if g not in genredocs:
                genredocs[g] = []
                genredates[g] = []
                genreauthors[g] = []
                allgenres.append(g)

            genredocs[g].append(docid)
            genredates[g].append(float(row['date']))
            genreauthors[g].append(row['author'])

            if g != 'random':
                if docid not in genredocs['allnonrandom']:
                    genredocs['allnonrandom'].append(docid)
                    genredates['allnonrandom'].append(float(row['date']))
                    genreauthors['allnonrandom'].append(row['author'])

            if docid not in all_genre_assigns:
                all_genre_assigns[docid] = []

            all_genre_assigns[docid].append(g)

for g in allgenres:
    genredates[g] = np.array(genredates[g])
    genredocs[g] = np.array(genredocs[g])
    genreauthors[g] = np.array(genreauthors[g])
    # that will allow us to mask

# ACTUAL MEASUREMENT

# Our process is as follows:

# select a docid randomly from the allnonrandom list
# get a genre assignment randomly from its list of genres
# select a docid from that genre list, masked by date
# measure in-genre distance
# select a docid from the random list, masked by date
# also one from the nonrandom list, masked by date
# measure both outgenre distances
# record this comparison

def get_doc_in_date_range(author, date, genre):
    global genredocs, genredates, genreauthors

    # let's select a docid that is no more than ten years earlier, no
    # more than ten years later, and *not* our original docid

    # returns the match, and the date of the selected docid

    mask = (genredates[genre] > (date - 10)) & (genredates[genre] < (date + 10)) & (genreauthors[genre] != author)

    candidates = genredocs[genre][mask]

    if len(candidates) < 1:
        return 'no match', 0, 'ge'
    else:
        match = random.sample(list(candidates), 1)[0]
        index = np.where(genredocs[genre] == match)
        newdate = genredates[genre][index][0]
        newauthor = genreauthors[genre][index][0]
        return match, newdate, newauthor

def get_doc_with_date_match(author, date, genre):
    global genredocs, genredates, all_genre_assigns

    # let's select a docid that exactly matches the
    # date of the original docid

    mask = (genredates[genre] == date) & (genreauthors[genre] != author)

    candidates = genredocs[genre][mask]

    if len(candidates) < 1:
        return 'no match'
    else:
        match = random.sample(list(candidates), 1)[0]
        return match

def get_random_doc(author, date, genrestoavoid):

    match = get_doc_with_date_match(author, date, 'random')

    if match == 'no match':
        return 'no match'

    genresofmatch = all_genre_assigns[match]

    for i in range(5):

        avoidthis = False

        for g in genresofmatch:
            if g == 'random' or g == 'allnonrandom':
                continue
            elif g in genrestoavoid:
                avoidthis = True

        if not avoidthis:
            return match

    return 'no match'

def measure_cosine(docA, docB):
    global vectors

    assert docA != docB

    return cosine(vectors[docA], vectors[docB])

def get_othergenredoc(genrestoavoid, author, date):

    for i in range(5):
        othermatch = get_doc_with_date_match(author, date, 'allnonrandom')
        genresofmatch = all_genre_assigns[othermatch]

        avoidthis = False

        for g in genresofmatch:
            if g == 'random' or g == 'allnonrandom':
                continue
            elif g in genrestoavoid:
                avoidthis = True

        if not avoidthis:
            return othermatch

    return 'no match'

failures = 0

results = list()

for i in range(40000):

    if i % 100 == 1:
        print(i)

    firstdoc = random.sample(list(genredocs['allnonrandom']), 1)[0]

    genre = random.sample(all_genre_assigns[firstdoc], 1)[0]
    firstdate = genredates[genre][genredocs[genre] == firstdoc][0]
    firstauthor = genreauthors[genre][genredocs[genre] == firstdoc][0]

    genrematch, genrematchdate, matchauthor = get_doc_in_date_range(firstauthor, firstdate, genre)

    if genrematch == 'no match':
        failures += 1
        continue

    datediff = abs(firstdate - genrematchdate)
    meandate = (firstdate + genrematchdate) / 2

    in_genre_dist = measure_cosine(firstdoc, genrematch)

    firstdocgenres = all_genre_assigns[firstdoc]
    genrematchgenres = all_genre_assigns[genrematch]

    fullyrandommatchA = get_random_doc(firstauthor, genrematchdate, firstdocgenres)
    fullyrandommatchB = get_random_doc(matchauthor, firstdate, genrematchgenres)

    othergenrematchA = get_othergenredoc(firstdocgenres, firstauthor, genrematchdate)
    othergenrematchB = get_othergenredoc(genrematchgenres, matchauthor, firstdate)

    if fullyrandommatchA == 'no match' or fullyrandommatchB == 'no match':
        failures += 1
        continue
    elif othergenrematchA == 'no match' or othergenrematchB == 'no match':
        failures += 1
        continue

    fully_random_dist_A = measure_cosine(firstdoc, fullyrandommatchA)
    fully_random_dist_B = measure_cosine(genrematch, fullyrandommatchB)

    fully_random_dist = (fully_random_dist_A + fully_random_dist_B) / 2

    other_genre_dist_A = measure_cosine(firstdoc, othergenrematchA)
    other_genre_dist_B = measure_cosine(genrematch, othergenrematchB)

    other_genre_dist = (other_genre_dist_A + other_genre_dist_B) / 2

    result = [genre, firstdoc, genrematch, sum(vectors[firstdoc]), sum(vectors[genrematch]), othergenrematchA, othergenrematchB, firstdate, genrematchdate, datediff, meandate, in_genre_dist, fully_random_dist, other_genre_dist, (fully_random_dist - in_genre_dist)/fully_random_dist, (other_genre_dist - in_genre_dist)/other_genre_dist, fullyrandommatchA, fullyrandommatchB]
    results.append(result)

with open('annotated_loc2_delta_results3.tsv', mode = 'w', encoding = 'utf-8') as f:
    f.write('genre\tfirstdoc\tgenrematch\tfirstlength\tmatchlength\tothermatchA\tothermatchB\tfirstdate\tmatchdate\tdatediff\tmeandate\tingenredist\tfullrandomdist\tothergenredist\tfullrandomdiff\tothergenrediff\trandommatchA\trandommatchB\n')
    for res in results:
        f.write('\t'.join([str(x) for x in res]) + '\n')
