# Linear Algebra: sample lecture notes (PLACEHOLDER)

These notes are a placeholder so the prototype runs out of the box. Replace this file with the real
course slides and notes (PDF, Markdown or text) before the demo.

## 1. Vectors and the dot product

### 1.1 Vectors

A vector in $R^n$ is an ordered list of $n$ real numbers, written as a column. Two vectors of the same
size are added component by component, and a vector is multiplied by a scalar by multiplying every
component. A linear combination of vectors $v_1, ..., v_k$ is any sum $c_1 v_1 + ... + c_k v_k$ with
scalars $c_i$.

### 1.2 Dot product and length

The dot product of $u$ and $v$ in $R^n$ is $u \cdot v = u_1 v_1 + ... + u_n v_n$. It is a single number,
not a vector. The length (norm) of $v$ is $||v|| = \sqrt{v \cdot v}$.

The dot product measures alignment: $u \cdot v = ||u|| \, ||v|| \cos\theta$, where $\theta$ is the angle
between the vectors. Two vectors are orthogonal (perpendicular) exactly when their dot product is 0.

### 1.3 Worked example: dot product

Let $u = (1, 2, 2)$ and $v = (2, 0, -1)$. Then $u \cdot v = 1 \cdot 2 + 2 \cdot 0 + 2 \cdot (-1) = 0$,
so $u$ and $v$ are orthogonal. The length of $u$ is $\sqrt{1 + 4 + 4} = 3$.

## 2. Matrices and matrix-vector products

### 2.1 Matrices

An $m \times n$ matrix has $m$ rows and $n$ columns. The transpose $A^T$ swaps rows and columns, so it
is $n \times m$. A matrix is symmetric when $A^T = A$.

### 2.2 Matrix times vector

The product $Ax$ is defined only when $A$ has as many columns as $x$ has entries. There are two ways to
read it. Row picture: entry $i$ of $Ax$ is the dot product of row $i$ of $A$ with $x$. Column picture:
$Ax$ is the linear combination of the columns of $A$ with the entries of $x$ as weights,
$Ax = x_1 a_1 + ... + x_n a_n$. The column picture is the one used most in machine learning: a
prediction $Xw$ is a weighted combination of the feature columns of $X$.

### 2.3 Matrix times matrix

The product $AB$ is defined when the number of columns of $A$ equals the number of rows of $B$. Entry
$(i, j)$ of $AB$ is the dot product of row $i$ of $A$ with column $j$ of $B$. In general
$AB \neq BA$: matrix multiplication is not commutative. The transpose of a product reverses the order:
$(AB)^T = B^T A^T$.

### 2.4 Worked example: matrix times vector

Let $A$ have rows $(1, 2)$ and $(3, 4)$, and let $x = (5, 6)$. Row picture:
$Ax = (1 \cdot 5 + 2 \cdot 6, \; 3 \cdot 5 + 4 \cdot 6) = (17, 39)$. Column picture:
$5 \cdot (1, 3) + 6 \cdot (2, 4) = (17, 39)$. Both give the same result.

## 3. Linear systems and Gaussian elimination

### 3.1 Linear systems

A linear system is written $Ax = b$. Solving it means finding weights $x$ such that the combination of
the columns of $A$ equals $b$. A system has no solution, exactly one solution, or infinitely many
solutions. It can never have exactly two.

### 3.2 Gaussian elimination

Gaussian elimination uses three row operations that do not change the solution set: swap two rows,
multiply a row by a non-zero number, and add a multiple of one row to another. The goal is row echelon
form, where every pivot (first non-zero entry of a row) is to the right of the pivot in the row above.
Then the system is solved from the last equation upwards by back substitution.

Columns with a pivot correspond to pivot variables; columns without a pivot correspond to free
variables. If there is a free variable and the system is consistent, there are infinitely many
solutions. A row of the form $0 = c$ with $c \neq 0$ means there is no solution.

### 3.3 Worked example: elimination

Solve $x + y = 3$, $2x + 3y = 8$. Subtract 2 times the first row from the second: $y = 2$. Back
substitution gives $x = 1$. Both columns have a pivot, so the solution is unique.

## 4. Inverse matrices and rank

### 4.1 The inverse

A square matrix $A$ is invertible if there is a matrix $A^{-1}$ with $A A^{-1} = A^{-1} A = I$. Then
$Ax = b$ has the unique solution $x = A^{-1} b$. A matrix is invertible exactly when elimination
produces a pivot in every column, which is the same as saying its columns are linearly independent.
For a product, $(AB)^{-1} = B^{-1} A^{-1}$.

### 4.2 Rank

The rank of a matrix is the number of pivots after elimination. It equals the number of linearly
independent columns and also the number of linearly independent rows. An $n \times n$ matrix is
invertible exactly when its rank is $n$ (full rank).

In data terms, if the feature matrix $X$ has a column that is a combination of other columns, $X$ does
not have full column rank. Then $X^T X$ is not invertible, and the least squares weights are not unique.

### 4.3 Worked example: rank

Let $A$ have rows $(1, 2)$ and $(2, 4)$. The second row is 2 times the first, so elimination leaves one
pivot. The rank is 1, the matrix is not invertible, and $Ax = b$ is solvable only when $b$ is a
multiple of $(1, 2)$.

## 5. Span, independence and basis

### 5.1 Span and linear independence

The span of a set of vectors is the set of all their linear combinations. Vectors $v_1, ..., v_k$ are
linearly independent if the only combination that gives the zero vector is the one with all weights
equal to 0. If one vector is a combination of the others, the set is dependent, and that vector adds
nothing to the span.

### 5.2 Basis and dimension

A basis of a subspace is a set of vectors that is linearly independent and spans the subspace. Every
vector of the subspace can be written in exactly one way as a combination of basis vectors. All bases
of the same subspace have the same number of vectors; this number is the dimension.

The column space of $A$ is the span of its columns; its dimension is the rank. The null space of $A$ is
the set of all $x$ with $Ax = 0$. For an $m \times n$ matrix, rank plus the dimension of the null space
equals $n$ (rank-nullity theorem).

### 5.3 Worked example: independence

Are $(1, 0, 1)$, $(0, 1, 1)$ and $(1, 1, 2)$ independent? The third is the sum of the first two, so
they are dependent. Their span is a plane (dimension 2), not all of $R^3$.

## 6. Orthogonality and projections

### 6.1 Projection onto a line

The projection of $b$ onto the line through $a$ is the closest point to $b$ on that line:
$p = \frac{a \cdot b}{a \cdot a} a$. The error $e = b - p$ is orthogonal to $a$. This orthogonality is
what makes $p$ the closest point.

### 6.2 Projection onto a column space and least squares

When $Ax = b$ has no solution, we look for the $\hat{x}$ that makes $A\hat{x}$ as close to $b$ as
possible. The closest point is the projection of $b$ onto the column space of $A$, and the error
$b - A\hat{x}$ must be orthogonal to every column of $A$: $A^T (b - A\hat{x}) = 0$. This gives the
normal equations $A^T A \hat{x} = A^T b$. If the columns of $A$ are independent, $A^T A$ is invertible
and $\hat{x} = (A^T A)^{-1} A^T b$.

This is exactly linear regression: $A$ is the data matrix, $b$ the targets, and $\hat{x}$ the weights
that minimise the squared error.

### 6.3 Worked example: projection

Project $b = (2, 3)$ onto $a = (1, 0)$. $a \cdot b = 2$ and $a \cdot a = 1$, so $p = (2, 0)$. The error
is $e = (0, 3)$, and $e \cdot a = 0$ as expected.

## 7. Determinants

### 7.1 Definition and meaning

The determinant is a number attached to a square matrix. For a $2 \times 2$ matrix with rows $(a, b)$
and $(c, d)$ it is $ad - bc$. Its absolute value is the factor by which the matrix scales areas (or
volumes in higher dimensions). A matrix is invertible exactly when its determinant is not 0: a zero
determinant means the matrix squashes space onto a lower dimension.

### 7.2 Properties

Swapping two rows changes the sign of the determinant. Adding a multiple of one row to another does not
change it. Multiplying a row by $c$ multiplies the determinant by $c$. For a triangular matrix the
determinant is the product of the diagonal entries, so elimination gives a fast way to compute it.
Also $\det(AB) = \det(A) \det(B)$ and $\det(A^T) = \det(A)$.

### 7.3 Worked example: determinant

For the matrix with rows $(2, 1)$ and $(4, 2)$: $\det = 2 \cdot 2 - 1 \cdot 4 = 0$. The rows are
dependent, the matrix is not invertible, and it maps the whole plane onto a single line.

## 8. Eigenvalues and eigenvectors

### 8.1 Definition

A non-zero vector $v$ is an eigenvector of a square matrix $A$ if $Av = \lambda v$ for some number
$\lambda$, called the eigenvalue. Multiplying by $A$ does not change the direction of an eigenvector;
it only stretches, shrinks or flips it by the factor $\lambda$.

### 8.2 How to find them

$Av = \lambda v$ is the same as $(A - \lambda I) v = 0$. A non-zero solution $v$ exists only when
$A - \lambda I$ is not invertible, that is when $\det(A - \lambda I) = 0$. This is the characteristic
equation. Solve it for $\lambda$, then for each $\lambda$ solve $(A - \lambda I) v = 0$ to get the
eigenvectors.

The sum of the eigenvalues equals the trace of $A$ (the sum of the diagonal), and their product equals
$\det(A)$. These two facts are a quick check on a computation.

### 8.3 Worked example: eigenvalues

Let $A$ have rows $(2, 1)$ and $(1, 2)$. $\det(A - \lambda I) = (2 - \lambda)^2 - 1 = 0$ gives
$\lambda = 1$ and $\lambda = 3$. For $\lambda = 3$: $(A - 3I) v = 0$ gives $v = (1, 1)$. For
$\lambda = 1$: $v = (1, -1)$. Check: the trace is 4 = 1 + 3 and the determinant is 3 = 1 times 3.

## 9. Diagonalization and symmetric matrices

### 9.1 Diagonalization

If an $n \times n$ matrix $A$ has $n$ linearly independent eigenvectors, put them as columns of a
matrix $V$ and the eigenvalues on the diagonal of $\Lambda$. Then $A = V \Lambda V^{-1}$. In the
basis of eigenvectors, $A$ acts as a simple scaling along each axis. Powers become easy:
$A^k = V \Lambda^k V^{-1}$.

### 9.2 Symmetric matrices and the spectral theorem

A real symmetric matrix always has real eigenvalues, and eigenvectors of different eigenvalues are
orthogonal. It can be written as $A = Q \Lambda Q^T$ with $Q$ orthogonal (its columns are orthonormal
eigenvectors). This is the spectral theorem.

### 9.3 Why PCA needs this

The covariance matrix of a data set is symmetric. Its eigenvectors are orthogonal directions in the
data, and each eigenvalue is the variance of the data along its eigenvector. PCA keeps the
eigenvectors with the largest eigenvalues: the directions in which the data varies the most.

### 9.4 Worked example: diagonalization

For $A$ with rows $(2, 1)$ and $(1, 2)$, the unit eigenvectors are $(1, 1)/\sqrt{2}$ and
$(1, -1)/\sqrt{2}$ with eigenvalues 3 and 1. They are orthogonal, as the spectral theorem promises,
and $A = Q \Lambda Q^T$ with these vectors as the columns of $Q$.
