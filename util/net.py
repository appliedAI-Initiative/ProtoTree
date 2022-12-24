import argparse

import torch.nn as nn
import torch.nn.functional as F

from features.densenet_features import (
    densenet121_features,
    densenet161_features,
    densenet169_features,
    densenet201_features,
)
from features.resnet_features import (
    ResNet_features,
    resnet18_features,
    resnet34_features,
    resnet50_features,
    resnet50_features_inat,
    resnet101_features,
    resnet152_features,
)
from features.vgg_features import (
    vgg11_bn_features,
    vgg11_features,
    vgg13_bn_features,
    vgg13_features,
    vgg16_bn_features,
    vgg16_features,
    vgg19_bn_features,
    vgg19_features,
)
from prototree.prototree import ProtoTree
from util.log import Log

base_architecture_to_features = {
    "resnet18": resnet18_features,
    "resnet34": resnet34_features,
    "resnet50": resnet50_features,
    "resnet50_inat": resnet50_features_inat,
    "resnet101": resnet101_features,
    "resnet152": resnet152_features,
    "densenet121": densenet121_features,
    "densenet161": densenet161_features,
    "densenet169": densenet169_features,
    "densenet201": densenet201_features,
    "vgg11": vgg11_features,
    "vgg11_bn": vgg11_bn_features,
    "vgg13": vgg13_features,
    "vgg13_bn": vgg13_bn_features,
    "vgg16": vgg16_features,
    "vgg16_bn": vgg16_bn_features,
    "vgg19": vgg19_features,
    "vgg19_bn": vgg19_bn_features,
}

# Create network with pretrained features and 1x1 convolutional layer
def get_network(num_features: int, net="resnet50_inat", pretrained=True):
    # Define a conv net for estimating the probabilities at each decision node
    features = base_architecture_to_features[net](pretrained=pretrained)
    first_add_on_layer_in_channels = get_add_on_layer_in_channels(features)

    add_on_layer = nn.Sequential(
        nn.Conv2d(
            in_channels=first_add_on_layer_in_channels,
            out_channels=num_features,
            kernel_size=1,
            bias=False,
        ),
        nn.Sigmoid(),
    )
    return features, add_on_layer


# TODO: fix signature and method
def get_add_on_layer_in_channels(features: ResNet_features):
    features_name = str(features).upper()
    if features_name.startswith("VGG") or features_name.startswith("RES"):
        first_add_on_layer_in_channels = [
            i for i in features.modules() if isinstance(i, nn.Conv2d)
        ][-1].out_channels
    elif features_name.startswith("DENSE"):
        first_add_on_layer_in_channels = [
            i for i in features.modules() if isinstance(i, nn.BatchNorm2d)
        ][-1].num_features
    else:
        raise Exception("other base base_architecture NOT implemented")
    return first_add_on_layer_in_channels


def freeze(
    epoch: int,
    params_to_freeze: list,
    log: Log,
    freeze_epochs: int,
):
    if freeze_epochs > 0:
        if epoch == 1:
            log.log_message("\nNetwork frozen")
            for parameter in params_to_freeze:
                parameter.requires_grad = False
        elif epoch == freeze_epochs + 1:
            log.log_message("\nNetwork unfrozen")
            for parameter in params_to_freeze:
                parameter.requires_grad = True
