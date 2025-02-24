import logging
from typing import Union

import numpy as np
import pandas as pd
import torch
import torch.optim
from torch.nn import functional as F
from torch.utils.data import DataLoader
from tqdm import tqdm

from src.core.models import ProtoPNet, ProtoTree
from src.core.types import SamplingStrat, SingleLeafStrat

log = logging.getLogger(__name__)


@torch.no_grad()
def eval_model(
    model: Union[ProtoPNet, ProtoTree],
    data_loader: DataLoader,
    strategy: SamplingStrat = "distributed",
    desc: str = "Evaluating",
    explain: bool = False,
) -> float:
    if isinstance(model, ProtoPNet):
        acc = eval_protopnet_model(
            model=model, data_loader=data_loader, desc=desc, explain=explain
        )

    elif isinstance(model, ProtoTree):
        acc = eval_prototree_model(
            model=model,
            data_loader=data_loader,
            strategy=strategy,
            desc=desc,
            explain=explain,
        )

    else:
        raise TypeError("Model type not recognised")

    return acc


@torch.no_grad()
def eval_protopnet_model(
    model: ProtoPNet,
    data_loader: DataLoader,
    desc: str = "Evaluating",
    explain: bool = False,
) -> float:
    """
    :param model:
    :param data_loader:
    :param strategy:
    :param desc: description for the progress bar, passed to tqdm
    :return:
    """
    model.eval()
    tqdm_loader = tqdm(data_loader, desc=desc, ncols=0)
    total_acc = 0.0
    n_batches = len(tqdm_loader)

    if explain:
        df_explanations = pd.DataFrame(
            columns=["image", "prototype", "modification", "delta", "orig_similarity"]
        )

    for batch_num, sample in enumerate(tqdm_loader):
        x, y = sample[0].to(model.device), sample[1].to(model.device)

        if explain:
            path = sample[2]
            x_mods = sample[3]
            dists = model.proto_base.forward(x)

            df_explanations_batch = prototypes_explanation(dists, path, x_mods, model)
            df_explanations = pd.concat(
                [df_explanations, df_explanations_batch], ignore_index=True
            )

            y_pred = torch.argmax(
                torch.softmax(F.log_softmax(model.classifier(dists), dim=1), dim=-1),
                dim=-1,
            )

        else:
            y_pred = model.predict(x)

        batch_acc = (y_pred == y).sum().item() / len(y)
        tqdm_loader.set_postfix_str(f"batch: acc={batch_acc:.5f}")
        total_acc += batch_acc

        if (
            batch_num == n_batches - 1
        ):  # TODO: Hack due to https://github.com/tqdm/tqdm/issues/1369
            avg_acc = total_acc / n_batches
            tqdm_loader.set_postfix_str(f"average: acc={avg_acc:.5f}")

    if explain:
        return avg_acc, df_explanations

    return avg_acc


@torch.no_grad()
def eval_prototree_model(
    model: ProtoTree,
    data_loader: DataLoader,
    strategy: SamplingStrat = "distributed",
    desc: str = "Evaluating",
    explain: bool = False,
) -> float:
    """
    :param tree:
    :param data_loader:
    :param strategy:
    :param desc: description for the progress bar, passed to tqdm
    :return:
    """
    model.eval()
    tqdm_loader = tqdm(data_loader, desc=desc, ncols=0)
    leaf_depths = []
    total_acc = 0.0
    n_batches = len(tqdm_loader)

    if explain:
        df_explanations = pd.DataFrame(
            columns=["image", "prototype", "modification", "delta", "orig_similarity"]
        )

    for batch_num, sample in enumerate(tqdm_loader):
        x, y = sample[0].to(model.device), sample[1].to(model.device)

        logits, _, predicting_leaves = model.forward(x, strategy=strategy)

        if explain:
            path = sample[2]
            x_mods = sample[3]
            dists = model.proto_base.forward(x)

            df_explanations_batch = prototypes_explanation(dists, path, x_mods, model)
            df_explanations = pd.concat(
                [df_explanations, df_explanations_batch], ignore_index=True
            )

        y_pred = torch.argmax(logits, dim=1)
        batch_acc = (y_pred == y).sum().item() / len(y)
        tqdm_loader.set_postfix_str(f"batch: acc={batch_acc:.5f}")
        total_acc += batch_acc

        # TODO: maybe factor out
        if predicting_leaves:
            leaf_depths.extend([leaf.depth for leaf in set(predicting_leaves)])

        if (
            batch_num == n_batches - 1
        ):  # TODO: Hack due to https://github.com/tqdm/tqdm/issues/1369
            avg_acc = total_acc / n_batches
            tqdm_loader.set_postfix_str(f"average: acc={avg_acc:.5f}")

    if leaf_depths:
        leaf_depths = np.array(leaf_depths)
        log.info(
            f"\nAverage path length is {leaf_depths.mean():.3f} with std {leaf_depths.std():.3f}"
        )
        log.info(
            f"Longest path has length {leaf_depths.max()}, shortest path has length {leaf_depths.min()}"
        )

    if explain:
        return avg_acc, df_explanations

    return avg_acc


@torch.no_grad()
def single_leaf_eval(
    projected_pruned_tree: ProtoTree,
    test_loader: DataLoader,
    eval_name: str,
):
    test_strategies: list[SingleLeafStrat] = ["sample_max"]
    for strategy in test_strategies:
        acc = eval_model(
            projected_pruned_tree,
            test_loader,
            strategy=strategy,
            desc=eval_name,
        )
        fidelity = eval_fidelity(projected_pruned_tree, test_loader, strategy)

        log.info(f"Accuracy of {strategy} routing: {acc:.3f}")
        log.info(f"Fidelity of {strategy} routing: {fidelity:.3f}")


@torch.no_grad()
def eval_fidelity(
    tree: ProtoTree,
    data_loader: DataLoader,
    test_strategy: SamplingStrat,
    ref_strategy: SamplingStrat = "distributed",
) -> float:
    n_batches = len(data_loader)
    tree.eval()
    avg_fidelity = 0.0
    for sample in tqdm(data_loader, desc="Evaluating fidelity", ncols=0):
        x, y = sample[0].to(tree.device), sample[1].to(tree.device)

        y_pred_reference = tree.predict(x, strategy=ref_strategy)
        y_pred_test = tree.predict(x, strategy=test_strategy)
        batch_fidelity = torch.sum(y_pred_reference == y_pred_test)
        avg_fidelity += batch_fidelity / (len(y) * n_batches)

    return avg_fidelity


@torch.no_grad()
def prototypes_explanation(dists, path, x_mods, model):
    """
    Compute prototype explanations

    :param dists: distances computed by the prototype layer in the network
    :param path: path of the image
    :param x_mods: dictionary of modified version of the input image
    :param model: used model (ProtoTree | ProtoPNet)

    :return dataframe with local scores
    """
    assert dists.shape[0] == 1, "Batch size has to be 1"

    data = dict(
        image=list(),
        prototype=list(),
        modification=list(),
        delta=list(),
        orig_similarity=list(),
    )

    n_proto = dists.shape[1]
    for mod, img_mod in x_mods.items():
        dists_mod = model.proto_base.forward(img_mod)
        local_scores = abs(dists - dists_mod)

        data["image"].extend(path * n_proto)
        data["prototype"].extend(list(range(n_proto)))
        data["modification"].extend([mod] * n_proto)
        data["delta"].extend(local_scores.cpu().numpy().reshape(-1))
        data["orig_similarity"].extend(dists.cpu().numpy().reshape(-1))

    return pd.DataFrame(data)
