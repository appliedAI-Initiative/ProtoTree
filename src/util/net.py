from src.features.densenet_features import *
from src.features.resnet_features import *
from src.features.vgg_features import *

NAME_TO_NET = {
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


def default_add_on_layers(feature_convnet: nn.Module, out_channels: int):
    conv_layer_1 = nn.Conv2d(
        in_channels=num_out_channels(feature_convnet),
        out_channels=out_channels,
        kernel_size=1,
    )
    torch.nn.init.kaiming_normal_(conv_layer_1.weight, nonlinearity="relu")
    conv_layer_2 = nn.Conv2d(
        in_channels=out_channels,
        out_channels=out_channels,
        kernel_size=1,
    )
    torch.nn.init.xavier_normal_(
        conv_layer_2.weight, gain=torch.nn.init.calculate_gain("sigmoid")
    )
    # TODO: Should we allow other activations? Why is the 2nd a sigmoid? Forcing [0, 1] due to relatively few layers
    #  after this one?
    return nn.Sequential(conv_layer_1, nn.ReLU(), conv_layer_2, nn.Sigmoid())


def num_out_channels(convnet: nn.Module):
    convnet_name = str(convnet).upper()
    if convnet_name.startswith("VGG") or convnet_name.startswith("RES"):
        n_out_channels = [i for i in convnet.modules() if isinstance(i, nn.Conv2d)][
            -1
        ].out_channels
    elif convnet_name.startswith("DENSE"):
        n_out_channels = [
            i for i in convnet.modules() if isinstance(i, nn.BatchNorm2d)
        ][-1].num_features
    else:
        raise ValueError(f"base_architecture {convnet_name} NOT implemented")
    return n_out_channels
