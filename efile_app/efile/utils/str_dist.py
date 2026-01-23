"""
A Levenshtein string distance function, for companing different option requests

https://en.wikipedia.org/wiki/Levenshtein_distance#Iterative_with_full_matrix
"""


def levenshtein_distance(str1, str2):
    if len(str1) == 0:
        return len(str2)
    if len(str2) == 0:
        return len(str1)

    matrix_rows = len(str1) + 1
    matrix_cols = len(str2) + 1

    matrix = [[0 for j in range(matrix_cols)] for i in range(matrix_rows)]

    for i in range(1, matrix_rows):
        matrix[i][0] = i

    for j in range(1, matrix_cols):
        matrix[0][j] = j

    for j in range(1, matrix_cols):
        for i in range(1, matrix_rows):
            if str1[i - 1] == str2[j - 1]:
                sub_cost = 0
            else:
                sub_cost = 1

            prev_row_val = matrix[i - 1][j]
            prev_col_val = matrix[i][j - 1]
            matrix[i][j] = min(prev_row_val + 1, prev_col_val + 1, matrix[i - 1][j - 1] + sub_cost)

    return matrix[len(str1)][len(str2)]
