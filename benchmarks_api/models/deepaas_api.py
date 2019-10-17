# -*- coding: utf-8 -*-
"""
Model description
"""

import argparse
import pkg_resources
import yaml
import json
import os
from tensorflow.python.client import device_lib

from werkzeug.exceptions import BadRequest

# import project's config.py
import benchmarks_api.config as cfg
import benchmark_cnn as benchmark
import cnn_util


local_gpus = []
num_local_gpus = 0

def get_metadata():
    """
    Function to read metadata
    """

    module = __name__.split('.', 1)

    pkg = pkg_resources.get_distribution(module[0])
    meta = {
        'Name': None,
        'Version': None,
        'Summary': None,
        'Home-page': None,
        'Author': None,
        'Author-email': None,
        'License': None,
    }

    for line in pkg.get_metadata_lines("PKG-INFO"):
        for par in meta:
            if line.startswith(par + ":"):
                _, value = line.split(": ", 1)
                meta[par] = value

    return meta


def predict_file(*args):
    """
    Function to make prediction on a local file
    """
    message = 'Not implemented in the model (predict_file)'
    return message


def predict_data(*args):
    """
    Function to make prediction on an uploaded file
    """
    message = 'Not implemented in the model (predict_data)'
    return message


def predict_url(*args):
    """
    Function to make prediction on a URL
    """
    message = 'Not implemented in the model (predict_url)'
    return message


###
# Uncomment the following two lines
# if you allow only authorized people to do training
###
# import flaat
# @flaat.login_required()
def train(train_args):
    """
    Train network
    train_args : dict
        Json dict with the user's configuration parameters.
        Can be loaded with json.loads() or with yaml.safe_load()    
    """

    run_results = {"status": "ok",
                   "train_args": {},
                   "training": {}
                   }

    # Remove possible existing model files
    for f in os.listdir(cfg.MODEL_DIR):
        file_path = os.path.join(cfg.MODEL_DIR, f)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(e)
    # Remove possible existing old metric file
    if os.path.isfile('{}/metric.log'):
        os.unlink('{}/metric.log'.format(cfg.DATA_DIR))


    kwargs = {'model': yaml.safe_load(train_args.model),
              'num_gpus': yaml.safe_load(train_args.num_gpus),
              'num_epochs': yaml.safe_load(train_args.num_epochs),
              'batch_size': yaml.safe_load(train_args.batch_size),
              'optimizer': yaml.safe_load(train_args.optimizer),
              'local_parameter_device': 'cpu',
              'variable_update': 'parameter_server',
              # 'benchmark_test_id': asdf,
              # 'log_dir': cfg.DATA_DIR,
              }

    # Locate training data
    if yaml.safe_load(train_args.dataset) != 'Synthetic data':
        kwargs['data_name'] = yaml.safe_load(train_args.dataset)
        kwargs['data_dir'] = cfg.DATA_DIR

    # If model is ResNet, chose the right number of layers
    if kwargs['model'] == 'resnet':
        if 'data_name' not in kwargs:
            kwargs['model'] = 'resnet50'
        elif kwargs['data_name'] == 'cifar10':
            kwargs['model'] = 'resnet56'
        else:
            kwargs['model'] = 'resnet50'

    # If no GPU is available or the gpu option is set to 0 run CPU mode
    if num_local_gpus == 0 or kwargs['num_gpus'] == 0:
        kwargs['device'] = 'cpu'
        kwargs['data_format'] = 'NHWC'  # cpu data format
        kwargs['num_gpus'] = 1  # Important: tensorflow uses this also to specify the number of CPUs
    else:
        kwargs['device'] = 'gpu'
        kwargs['data_format'] = 'NCHW'


    # Return training args as result but not directories
    run_results["train_args"] = kwargs
    kwargs['train_dir'] = cfg.MODEL_DIR
    kwargs['benchmark_log_dir'] = cfg.DATA_DIR

    params = benchmark.make_params(**kwargs)

    # Setup and run the benchmark model
    try:
        params = benchmark.setup(params)
        bench = benchmark.BenchmarkCNN(params)
    except ValueError as param_ex:
        raise BadRequest("ValueError: {}".format(param_ex))

    tfversion = '.'.join([str(x) for x in cnn_util.tensorflow_version_tuple()])
    run_results["training"]["tf_version"] = tfversion

    bench.print_info()
    bench.run()

    # Read log file and get training results
    logfile = '{}/metric.log'.format(cfg.DATA_DIR)
    with open(logfile, "r") as f:
        for line in f:
            pass
        result = json.loads(line)
        avg_examples = result["value"]
        run_results["training"]["average_examples_per_sec"] = avg_examples



    ## Evaluation ##
    if yaml.safe_load(train_args.evaluation):
        run_results["evaluation"] = {}

        kwargs_eval = {'model': kwargs['model'],
                       'num_gpus': kwargs['num_gpus'],
                       'device': kwargs['device'],
                       'data_format': kwargs['data_format'],
                       'benchmark_log_dir': kwargs['benchmark_log_dir'],
                       'train_dir': kwargs['train_dir'],
                       'eval': True
                       # 'eval_dir': cfg.DATA_DIR,
                       # 'benchmark_test_id': asdf,
                       }

        # Locate data
        if yaml.safe_load(train_args.dataset) != 'Synthetic data':
            kwargs_eval['data_name'] = kwargs['data_name']
            kwargs_eval['data_dir'] = kwargs['data_dir']

        # Setup and run the evaluation
        params_eval = benchmark.make_params(**kwargs_eval)
        try:
            params_eval = benchmark.setup(params_eval)
            evaluation = benchmark.BenchmarkCNN(params_eval)
        except ValueError as param_ex:
            raise BadRequest("ValueError: {}".format(param_ex))

        evaluation.print_info()
        evaluation.run()

        # Read log file and get evaluation results
        logfile = '{}/metric.log'.format(cfg.DATA_DIR)
        with open(logfile, "r") as f:
            for line in f:
                l = json.loads(line)
                if l["name"] == "eval_average_examples_per_sec":
                    run_results["evaluation"]["average_examples_per_sec"] = l["value"]
                if l["name"] == "eval_top_1_accuracy":
                    run_results["evaluation"]["top_1_accuracy"] = l["value"]
                if l["name"] == "eval_top_5_accuracy":
                    run_results["evaluation"]["top_5_accuracy"] = l["value"]

    return run_results


def get_train_args():
    """
    Returns a dict of dicts to feed the deepaas API parser
    """
    train_args = cfg.train_args
    global local_gpus, num_local_gpus

    # convert default values and possible 'choices' into strings
    for key, val in train_args.items():
        val['default'] = str(val['default'])  # yaml.safe_dump(val['default']) #json.dumps(val['default'])
        if 'choices' in val:
            val['choices'] = [str(item) for item in val['choices']]


    # Adjust num_gpu option accordingly to available local devices
    local_devices = device_lib.list_local_devices()
    local_gpus = [x for x in local_devices if x.device_type == 'GPU']
    num_local_gpus = len(local_gpus)

    train_args['num_gpus']['choices'] = ['0']
    if num_local_gpus == 0:
        train_args['num_gpus']['default'] = '0'
    else:
        train_args['num_gpus']['default'] = '1'
        for i in range(num_local_gpus): train_args['num_gpus']['choices'].append(str(i+1))


    return train_args


# !!! deepaas>=0.5.0 calls get_test_args() to get args for 'predict'
def get_test_args():
    predict_args = cfg.predict_args

    # convert default values and possible 'choices' into strings
    for key, val in predict_args.items():
        val['default'] = str(val['default'])  # yaml.safe_dump(val['default']) #json.dumps(val['default'])
        if 'choices' in val:
            val['choices'] = [str(item) for item in val['choices']]

    return predict_args


# during development it might be practical
# to check your code from the command line
def main():
    """
       Runs above-described functions depending on input parameters
       (see below an example)
    """

    if args.method == 'get_metadata':
        get_metadata()
    elif args.method == 'train':
        train(args)
    else:
        get_metadata()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Model parameters')

    # get arguments configured for get_train_args()
    train_args = get_train_args()
    for key, val in train_args.items():
        parser.add_argument('--%s' % key,
                            default=val['default'],
                            type=type(val['default']),
                            help=val['help'])

    parser.add_argument('--method', type=str, default="get_metadata",
                        help='Method to use: get_metadata (default), \
                        predict_file, predict_data, predict_url, train')
    args = parser.parse_args()

    main()
