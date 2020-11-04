"""Trains a model, saving checkpoints and tensorboard summaries along
   the way."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from datetime import datetime
import json
import os
import shutil
from timeit import default_timer as timer

import tensorflow.compat.v1 as tf
tf.disable_v2_behavior()
import numpy as np
import input_data
import itertools
import utils_model
import utils_print

import argparse

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("--batch_range", type=int, nargs='+', default=[64],
                            help="batch range")

parser.add_argument("--ratio_range", type=float, nargs='+', default=[0.8],
                            help="ratio range")

parser.add_argument("--model", "-m", type=str, required=True, choices=["ff", "cnn"],
                            help="model type, either ff or cnn")

parser.add_argument("--stable", action="store_true",
                            help="stable version")

parser.add_argument("--dropout", type=float, default=1,
                            help="dropout rate, 1 is no dropout, 0 is all set to 0")

parser.add_argument("--l2", type=float, default=0,
                            help="l2 regularization rate")

parser.add_argument("--l0", type=float, default=0,
                            help="l0 regularization rate")

parser.add_argument("--reg_stability", type=float, default=0,
                            help="reg stability regularization rate")

parser.add_argument("--num_subsets", type=int, default=1,
                            help="number of subsets for Monte Carlo")

parser.add_argument("--l1_size", type=int, default=512,
                            help="number of nodes in the first layer, 784 -> l1_size")

parser.add_argument("--l2_size", type=int, default=256,
                            help="number of nodes in the first layer, l1_size -> l2_size")

parser.add_argument("--cnn_size", type=int, default=32,
                            help="number of filters in the cnn layers for cnn")

parser.add_argument("--fc_size", type=int, default=128,
                            help="number of nodes in the dense layer for cnn")

parser.add_argument("--data_set", type=str, default="mnist",
                            help="number of subsets")

parser.add_argument("--MC", action="store_true",
                            help="Monte Carlo version")

parser.add_argument("--train_size", type=float, default=1,
                            help="training percent of the data")

parser.add_argument("--val_size", type=float, default=0.25,
                            help="validation percent of the data e.g., 0.25 means 0.25*traning size")

with open('config.json') as config_file:
    config = json.load(config_file)


args = parser.parse_args()
print(args)
if args.model == "ff":
    from NN_model import Model
elif args.model == "cnn":
    from CNN_model import Model
    assert(tf.keras.backend.image_data_format() == "channels_last")
# Setting up training parameters
seed = config['random_seed']
tf.set_random_seed(seed)
max_num_training_steps = config['max_num_training_steps']
num_output_steps = config['num_output_steps']
num_summary_steps = config['num_summary_steps']
num_checkpoint_steps = config['num_checkpoint_steps']
testing_size = config['testing_size']
data_set = args.data_set
num_subsets = args.num_subsets
initial_learning_rate = config['initial_learning_rate']
eta = config['constant_learning_rate']
learning_rate = tf.train.exponential_decay(initial_learning_rate,
 0, 5, 0.85, staircase=True)

global_step = tf.Variable(1, name="global_step")


for batch_size, subset_ratio in itertools.product(args.batch_range, args.ratio_range): #Parameters chosen with validation
  print(batch_size, subset_ratio, args.dropout)

  #Setting up the data and the model
  if args.model == "ff":
      data = input_data.load_data_set(training_size = args.train_size, validation_size=args.val_size, data_set=data_set, seed=seed)
      num_features = data.train.images.shape[1]
      model = Model(num_subsets, batch_size, args.l1_size, args.l2_size, subset_ratio, num_features, args.dropout, args.l2, args.l0, args.reg_stability)
      var_list = [model.W1, model.b1, model.W2, model.b2, model.W3, model.b3]
  elif args.model == "cnn":
      data = input_data.load_data_set(training_size = args.train_size, validation_size=args.val_size, data_set=data_set, reshape=False, seed=seed)
      print(data.train.images.shape)
      pixels_x = data.train.images.shape[1]
      pixels_y = data.train.images.shape[2]
      num_channels = data.train.images.shape[3]

      theta = args.stable and (not args.MC)

      model = Model(num_subsets, batch_size, args.cnn_size, args.fc_size, subset_ratio, pixels_x, pixels_y, num_channels, args.dropout, args.l2, theta)

  #Returns the right loss depending on MC or dual or nothing
  max_loss = utils_model.get_loss(model, args)

  #Setting up data for testing and validation
  val_dict = {model.x_input: data.validation.images,
                  model.y_input: data.validation.labels.reshape(-1)}
  test_dict = {model.x_input: data.test.images[:testing_size],
                  model.y_input: data.test.labels[:testing_size].reshape(-1)}

  # Setting up the optimizer
  if args.model == "ff":
    optimizer = tf.train.AdamOptimizer(eta).minimize(max_loss + model.regularizer, global_step=global_step, var_list=var_list)
  elif args.model == "cnn":
    optimizer = tf.train.AdamOptimizer(eta).minimize(max_loss + model.regularizer, global_step=global_step)

  #Initializing loop variables.
  avg_test_acc = 0
  num_experiments = config['num_experiments']
  dict_exp = utils_model.create_dict(args, data.train.images.shape, data.test.images.shape)

  for experiment in range(num_experiments):
    print("Experiment", experiment)
    
    with tf.Session() as sess:
          sess.run(tf.global_variables_initializer())
          training_time = 0.0
    
          # Main training loop
          best_val_acc, test_acc, num_iters = 0, 0, 0

          for ii in range(max_num_training_steps):
            x_batch, y_batch = data.train.next_batch(batch_size)
            if args.model == "cnn":
                y_batch = y_batch.reshape(-1)
            nat_dict = {model.x_input: x_batch,
                        model.y_input: y_batch}
    
            # Output
            if ii % num_output_steps == 0:
              val_acc = utils_print.print_metrics(sess, model, nat_dict, val_dict, ii, args)
              #Validation
              if val_acc > best_val_acc:
                print("New best val acc is", val_acc)
                best_val_acc = val_acc
                num_iters = ii
                test_acc = sess.run(model.accuracy, feed_dict=test_dict)
                print("New best test acc is", test_acc)
                dict_exp = utils_model.update_dict(dict_exp, args, sess, model, test_dict, experiment)

              if ii != 0:
                print('    {} examples per second'.format(
                    num_output_steps * batch_size / training_time))
                training_time = 0.0

            # Actual training step
            start = timer()
            sess.run(optimizer, feed_dict=nat_dict)
            end = timer()
            training_time += end - start
    
    
          #Output test results
          utils_print.update_dict_output(dict_exp, experiment, sess, test_acc, model, test_dict, num_iters)
          avg_test_acc += test_acc

  utils_print.print_stability_measures(dict_exp, args, num_experiments, batch_size, subset_ratio, avg_test_acc, max_num_training_steps)
