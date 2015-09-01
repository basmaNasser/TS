/* Copyright (C) 2014 Ion Torrent Systems, Inc. All Rights Reserved */

#ifndef POLYCLONAL_FILTER_H
#define POLYCLONAL_FILTER_H

class PolyclonalFilterOpts {
  public:
    PolyclonalFilterOpts();

    bool enable;
    int mixed_first_flow;
    int mixed_last_flow;
    int max_iterations;
    int mixed_model_option;
    double mixed_stringency;
    bool verbose;
    bool use_last_iter_params;
    bool filter_extreme_ppf_only;
};

#endif // POLYCLONAL_FILTER_H
