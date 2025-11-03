import argparse

import matplotlib.pyplot as plt
import numpy as np


def generate_sierpinski(n_points=50000, burn_in=10, seed=None):
    if seed is not None:
        np.random.seed(seed)

    maps = [
        (0.5, 0.0, 0.0, 0.5, 0.0, 0.0),
        (0.5, 0.0, 0.0, 0.5, 0.5, 0.0),
        (0.5, 0.0, 0.0, 0.5, 0.25, np.sqrt(3)/4.0),
    ]

    probs = np.array([1/3, 1/3, 1/3])
    cum_probs = np.cumsum(probs)

    total_iters = burn_in + n_points

    xs = np.empty(n_points, dtype=np.float64)
    ys = np.empty(n_points, dtype=np.float64)

    x, y = 0.0, 0.0

    out_idx = 0
    for i in range(total_iters):
        r = np.random.rand()
        idx = np.searchsorted(cum_probs, r)
        a, b, c, d, e, f = maps[idx]

        x_new = a * x + b * y + e
        y_new = c * x + d * y + f
        x, y = x_new, y_new

        if i >= burn_in:
            xs[out_idx] = x
            ys[out_idx] = y
            out_idx += 1

    return xs, ys


def plot_points(xs, ys, figsize=(6, 6), dot_size=0.2):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    colors = ys
    ax.scatter(xs, ys, s=dot_size, c=colors, cmap="inferno", marker=".", linewidths=0)

    plt.show()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sierpinski triangle via IFS (iterated function system).")
    parser.add_argument('-n', '--points', type=int, default=100_000,
                        help='number of points to generate (default: 100000)')
    parser.add_argument('-b', '--burn', type=int, default=10,
                        help='burn-in iterations to discard (default: 10)')
    parser.add_argument('-s', '--seed', type=int, default=None,
                        help='random seed for reproducibility (default: None)')
    parser.add_argument('--dotsize', type=float, default=0.2,
                        help='scatter dot size (default: 0.2)')

    args = parser.parse_args(argv)

    xs, ys = generate_sierpinski(n_points=args.points, burn_in=args.burn, seed=args.seed)
    plot_points(xs, ys, dot_size=args.dotsize)


if __name__ == '__main__':
    main()