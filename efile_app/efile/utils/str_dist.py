"""
A Levenshtein string distance function, for companing different option requests
"""

def levenshtein_distance(str1, str2):
    if len(str1) == 0:
        return len(str2)
    if len(str2) == 0:
        return len(str1)

    end_str1 = len(str1) + 1
    end_str2 = len(str2) + 1

    matrix = [[0 for j in range(end_str2)] for i in range(end_str1)]

    for i in range(1, end_str1):
        matrix[i][0] = i

    for j in range(1, end_str2):
        matrix[0][j] = j

    for j in range(1, end_str2):
        for i in range(1, end_str1):
            if str1[i - 1] == str2[j - 1]:
                sub_cost = 0
            else:
                sub_cost = 1

            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + sub_cost
            )

    return matrix[len(str1)][len(str2)]
