window.JEV_COMPOSITE = {
 "schema_version": 1,
 "generated_at": "2026-10-30T04:18:46.934516+00:00",
 "source": {
  "benchmark": "benchmark.json",
  "telemetry": "telemetry.json",
  "benchmark_updated_at": "2026-10-30T04:18:46.864254+00:00",
  "configurations": 56,
  "telemetry_runs": 1176,
  "seeds": 3,
  "procedure": "SUMO, 3,600 s episode, 240 control steps, 3 seeds per condition"
 },
 "method": {
  "normalisation": "Per (flow, metric) log min-max over every published configuration. Best observed = 100, worst observed = 0.",
  "aggregation": "Unweighted mean of the 21 cell scores (7 flows x 3 metrics).",
  "cost": "Per flow: median over the three seeds of serving time x GPUs held; then averaged over the seven flows.",
  "frontier": "Configurations not dominated on (cost, score) among self-hosted models."
 },
 "metrics": [
  {
   "key": "att",
   "label": "Travel time"
  },
  {
   "key": "awt",
   "label": "Waiting time"
  },
  {
   "key": "aql",
   "label": "Queue length"
  }
 ],
 "flows": [
  {
   "id": "jinan-1",
   "name": "Jinan 1",
   "intersections": 12
  },
  {
   "id": "jinan-2",
   "name": "Jinan 2",
   "intersections": 12
  },
  {
   "id": "jinan-3",
   "name": "Jinan 3",
   "intersections": 12
  },
  {
   "id": "hangzhou-1",
   "name": "Hangzhou 1",
   "intersections": 16
  },
  {
   "id": "hangzhou-2",
   "name": "Hangzhou 2",
   "intersections": 16
  },
  {
   "id": "newyork-1",
   "name": "New York 1",
   "intersections": 196
  },
  {
   "id": "newyork-2",
   "name": "New York 2",
   "intersections": 196
  }
 ],
 "columns": [
  {
   "flow": "jinan-1",
   "metric": "att",
   "min": 317.435001323802,
   "max": 1495.6235263190722
  },
  {
   "flow": "jinan-1",
   "metric": "awt",
   "min": 56.147153825787655,
   "max": 1346.5418937154132
  },
  {
   "flow": "jinan-1",
   "metric": "aql",
   "min": 97.91185185185185,
   "max": 1616.1698148148148
  },
  {
   "flow": "jinan-2",
   "metric": "att",
   "min": 302.5954944635357,
   "max": 1588.2638548384623
  },
  {
   "flow": "jinan-2",
   "metric": "awt",
   "min": 38.4684230622375,
   "max": 1434.8384075534798
  },
  {
   "flow": "jinan-2",
   "metric": "aql",
   "min": 46.47935185185185,
   "max": 1349.765462962963
  },
  {
   "flow": "jinan-3",
   "metric": "att",
   "min": 297.7138696760102,
   "max": 1451.3851544743206
  },
  {
   "flow": "jinan-3",
   "metric": "awt",
   "min": 42.88957650770538,
   "max": 1305.5653892045923
  },
  {
   "flow": "jinan-3",
   "metric": "aql",
   "min": 65.24157407407408,
   "max": 1450.8055555555557
  },
  {
   "flow": "hangzhou-1",
   "metric": "att",
   "min": 341.36015197228744,
   "max": 1539.3667894729172
  },
  {
   "flow": "hangzhou-1",
   "metric": "awt",
   "min": 25.1660520728573,
   "max": 1366.7749857910435
  },
  {
   "flow": "hangzhou-1",
   "metric": "aql",
   "min": 20.785648148148145,
   "max": 799.2975
  },
  {
   "flow": "hangzhou-2",
   "metric": "att",
   "min": 370.36415700780816,
   "max": 1059.8506250770713
  },
  {
   "flow": "hangzhou-2",
   "metric": "awt",
   "min": 64.72852479920827,
   "max": 901.2342105797162
  },
  {
   "flow": "hangzhou-2",
   "metric": "aql",
   "min": 106.87694444444445,
   "max": 895.9750925925925
  },
  {
   "flow": "newyork-1",
   "metric": "att",
   "min": 883.6508272354405,
   "max": 2019.612930874504
  },
  {
   "flow": "newyork-1",
   "metric": "awt",
   "min": 413.56745619751314,
   "max": 1892.347889960563
  },
  {
   "flow": "newyork-1",
   "metric": "aql",
   "min": 1042.1662962962964,
   "max": 3429.0191666666665
  },
  {
   "flow": "newyork-2",
   "metric": "att",
   "min": 1143.098173105949,
   "max": 2140.07636116702
  },
  {
   "flow": "newyork-2",
   "metric": "awt",
   "min": 688.1800860775174,
   "max": 2010.879345296659
  },
  {
   "flow": "newyork-2",
   "metric": "aql",
   "min": 2170.0826851851853,
   "max": 4661.039259259259
  }
 ],
 "modes": [
  {
   "id": "cojevlight",
   "label": "CoJevLight"
  },
  {
   "id": "jevlight",
   "label": "JevLight"
  }
 ],
 "configs": [
  {
   "id": "d3-flash::cojevlight",
   "model": "d3-flash",
   "mode": "cojevlight",
   "name": "D3 Flash",
   "family": "d3",
   "family_label": "D3",
   "color": "#4dd0e1",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 98.1,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 319.035,
      "sd": 1.955,
      "score": 99.68
     },
     "awt": {
      "raw": 58.25,
      "sd": 1.408,
      "score": 98.84
     },
     "aql": {
      "raw": 101.605,
      "sd": 2.454,
      "score": 98.68
     }
    },
    "jinan-2": {
     "att": {
      "raw": 306.369,
      "sd": 0.874,
      "score": 99.25
     },
     "awt": {
      "raw": 42.394,
      "sd": 0.312,
      "score": 97.31
     },
     "aql": {
      "raw": 51.242,
      "sd": 0.376,
      "score": 97.1
     }
    },
    "jinan-3": {
     "att": {
      "raw": 300.735,
      "sd": 0.063,
      "score": 99.36
     },
     "awt": {
      "raw": 46.081,
      "sd": 0.262,
      "score": 97.9
     },
     "aql": {
      "raw": 70.115,
      "sd": 0.397,
      "score": 97.68
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 350.565,
      "sd": 0.983,
      "score": 98.23
     },
     "awt": {
      "raw": 34.115,
      "sd": 0.271,
      "score": 92.38
     },
     "aql": {
      "raw": 28.217,
      "sd": 0.222,
      "score": 91.62
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 374.052,
      "sd": 1.864,
      "score": 99.06
     },
     "awt": {
      "raw": 69.952,
      "sd": 1.349,
      "score": 97.05
     },
     "aql": {
      "raw": 116.574,
      "sd": 1.847,
      "score": 95.92
     }
    },
    "newyork-1": {
     "att": {
      "raw": 883.651,
      "sd": 7.205,
      "score": 100.0
     },
     "awt": {
      "raw": 413.567,
      "sd": 11.408,
      "score": 100.0
     },
     "aql": {
      "raw": 1042.166,
      "sd": 29.973,
      "score": 100.0
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1143.098,
      "sd": 7.539,
      "score": 100.0
     },
     "awt": {
      "raw": 688.18,
      "sd": 7.498,
      "score": 100.0
     },
     "aql": {
      "raw": 2170.083,
      "sd": 30.632,
      "score": 100.0
     }
    }
   },
   "cost": {
    "gpu_seconds": 4155.2,
    "serving_seconds": 1439.8,
    "wall_seconds": 1580.7,
    "tokens_per_task": 27350923,
    "decisions_per_task": 12736,
    "tokens_per_decision": 2147.5,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1441.3,
     "jinan-2": 1260.9,
     "jinan-3": 1353.9,
     "hangzhou-1": 1269.6,
     "hangzhou-2": 1467.8,
     "newyork-1": 11070.9,
     "newyork-2": 11221.7
    }
   },
   "rank": 1,
   "pareto": true
  },
  {
   "id": "clef-flash::cojevlight",
   "model": "clef-flash",
   "mode": "cojevlight",
   "name": "Clef Flash",
   "family": "clef",
   "family_label": "Clef",
   "color": "#ff8a65",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 93.05,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 318.912,
      "sd": 0.933,
      "score": 99.7
     },
     "awt": {
      "raw": 57.154,
      "sd": 0.945,
      "score": 99.44
     },
     "aql": {
      "raw": 99.697,
      "sd": 1.651,
      "score": 99.36
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.027,
      "sd": 0.37,
      "score": 99.91
     },
     "awt": {
      "raw": 39.022,
      "sd": 0.706,
      "score": 99.61
     },
     "aql": {
      "raw": 47.149,
      "sd": 0.856,
      "score": 99.58
     }
    },
    "jinan-3": {
     "att": {
      "raw": 297.714,
      "sd": 0.895,
      "score": 100.0
     },
     "awt": {
      "raw": 42.898,
      "sd": 0.433,
      "score": 99.99
     },
     "aql": {
      "raw": 65.262,
      "sd": 0.659,
      "score": 99.99
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 342.643,
      "sd": 1.249,
      "score": 99.75
     },
     "awt": {
      "raw": 26.516,
      "sd": 0.72,
      "score": 98.69
     },
     "aql": {
      "raw": 21.912,
      "sd": 0.587,
      "score": 98.55
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 376.304,
      "sd": 0.921,
      "score": 98.49
     },
     "awt": {
      "raw": 66.488,
      "sd": 0.779,
      "score": 98.98
     },
     "aql": {
      "raw": 109.356,
      "sd": 1.071,
      "score": 98.92
     }
    },
    "newyork-1": {
     "att": {
      "raw": 978.107,
      "sd": 2.981,
      "score": 87.71
     },
     "awt": {
      "raw": 534.503,
      "sd": 3.409,
      "score": 83.13
     },
     "aql": {
      "raw": 1375.717,
      "sd": 10.77,
      "score": 76.69
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1320.308,
      "sd": 4.718,
      "score": 77.02
     },
     "awt": {
      "raw": 914.384,
      "sd": 8.319,
      "score": 73.5
     },
     "aql": {
      "raw": 2832.805,
      "sd": 22.876,
      "score": 65.14
     }
    }
   },
   "cost": {
    "gpu_seconds": 2062.7,
    "serving_seconds": 645.0,
    "wall_seconds": 778.9,
    "tokens_per_task": null,
    "decisions_per_task": 12691,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 645.0,
     "jinan-2": 590.8,
     "jinan-3": 626.3,
     "hangzhou-1": 620.0,
     "hangzhou-2": 690.0,
     "newyork-1": 5528.1,
     "newyork-2": 5738.8
    }
   },
   "rank": 2,
   "pareto": true
  },
  {
   "id": "jev-api::cojevlight",
   "model": "jev-api",
   "mode": "cojevlight",
   "name": "Jev API",
   "family": "jev-api",
   "family_label": "Jev API",
   "color": "#e8eef5",
   "kind": "api",
   "hosted": true,
   "params_b": null,
   "score": 92.93,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 319.451,
      "sd": 0.948,
      "score": 99.59
     },
     "awt": {
      "raw": 57.603,
      "sd": 0.292,
      "score": 99.19
     },
     "aql": {
      "raw": 100.471,
      "sd": 0.53,
      "score": 99.08
     }
    },
    "jinan-2": {
     "att": {
      "raw": 302.595,
      "sd": 0.949,
      "score": 100.0
     },
     "awt": {
      "raw": 38.468,
      "sd": 0.265,
      "score": 100.0
     },
     "aql": {
      "raw": 46.479,
      "sd": 0.323,
      "score": 100.0
     }
    },
    "jinan-3": {
     "att": {
      "raw": 297.831,
      "sd": 0.549,
      "score": 99.98
     },
     "awt": {
      "raw": 42.967,
      "sd": 0.341,
      "score": 99.95
     },
     "aql": {
      "raw": 65.375,
      "sd": 0.507,
      "score": 99.93
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 343.273,
      "sd": 1.237,
      "score": 99.63
     },
     "awt": {
      "raw": 26.978,
      "sd": 0.518,
      "score": 98.26
     },
     "aql": {
      "raw": 22.293,
      "sd": 0.431,
      "score": 98.08
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 371.491,
      "sd": 1.935,
      "score": 99.71
     },
     "awt": {
      "raw": 66.906,
      "sd": 0.912,
      "score": 98.74
     },
     "aql": {
      "raw": 113.216,
      "sd": 1.709,
      "score": 97.29
     }
    },
    "newyork-1": {
     "att": {
      "raw": 978.651,
      "sd": 7.654,
      "score": 87.65
     },
     "awt": {
      "raw": 534.071,
      "sd": 5.947,
      "score": 83.19
     },
     "aql": {
      "raw": 1399.387,
      "sd": 18.817,
      "score": 75.25
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1308.508,
      "sd": 12.089,
      "score": 78.45
     },
     "awt": {
      "raw": 902.216,
      "sd": 13.465,
      "score": 74.75
     },
     "aql": {
      "raw": 2883.089,
      "sd": 33.978,
      "score": 62.84
     }
    }
   },
   "cost": {
    "gpu_seconds": null,
    "serving_seconds": 572.1,
    "wall_seconds": null,
    "tokens_per_task": 33871658,
    "decisions_per_task": 12589,
    "tokens_per_decision": 2690.5,
    "gpus": null,
    "hosted": true,
    "runs": 21,
    "by_flow": {
     "jinan-1": null,
     "jinan-2": null,
     "jinan-3": null,
     "hangzhou-1": null,
     "hangzhou-2": null,
     "newyork-1": null,
     "newyork-2": null
    }
   },
   "rank": 3,
   "pareto": false
  },
  {
   "id": "pplx-decider-flash-v1.2::cojevlight",
   "model": "pplx-decider-flash-v1.2",
   "mode": "cojevlight",
   "name": "PPLX Decider Flash v1.2",
   "family": "pplx",
   "family_label": "PPLX",
   "color": "#f06292",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 92.38,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 321.578,
      "sd": 1.338,
      "score": 99.16
     },
     "awt": {
      "raw": 59.159,
      "sd": 0.858,
      "score": 98.36
     },
     "aql": {
      "raw": 103.205,
      "sd": 1.513,
      "score": 98.12
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.623,
      "sd": 1.132,
      "score": 99.8
     },
     "awt": {
      "raw": 39.383,
      "sd": 0.466,
      "score": 99.35
     },
     "aql": {
      "raw": 47.591,
      "sd": 0.569,
      "score": 99.3
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.768,
      "sd": 0.948,
      "score": 99.78
     },
     "awt": {
      "raw": 43.569,
      "sd": 0.42,
      "score": 99.54
     },
     "aql": {
      "raw": 66.293,
      "sd": 0.638,
      "score": 99.48
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 346.049,
      "sd": 0.887,
      "score": 99.09
     },
     "awt": {
      "raw": 29.656,
      "sd": 0.134,
      "score": 95.89
     },
     "aql": {
      "raw": 24.517,
      "sd": 0.105,
      "score": 95.48
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 373.642,
      "sd": 1.711,
      "score": 99.16
     },
     "awt": {
      "raw": 71.417,
      "sd": 3.545,
      "score": 96.27
     },
     "aql": {
      "raw": 115.297,
      "sd": 5.408,
      "score": 96.43
     }
    },
    "newyork-1": {
     "att": {
      "raw": 987.182,
      "sd": 7.367,
      "score": 86.6
     },
     "awt": {
      "raw": 545.104,
      "sd": 7.542,
      "score": 81.84
     },
     "aql": {
      "raw": 1400.048,
      "sd": 16.586,
      "score": 75.21
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1303.584,
      "sd": 9.024,
      "score": 79.05
     },
     "awt": {
      "raw": 896.288,
      "sd": 13.27,
      "score": 75.36
     },
     "aql": {
      "raw": 2800.659,
      "sd": 27.904,
      "score": 66.63
     }
    }
   },
   "cost": {
    "gpu_seconds": 3324.9,
    "serving_seconds": 1144.0,
    "wall_seconds": 1284.0,
    "tokens_per_task": 27382794,
    "decisions_per_task": 12790,
    "tokens_per_decision": 2140.9,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1150.4,
     "jinan-2": 998.6,
     "jinan-3": 1074.5,
     "hangzhou-1": 1005.3,
     "hangzhou-2": 1175.1,
     "newyork-1": 8782.2,
     "newyork-2": 9088.1
    }
   },
   "rank": 4,
   "pareto": false
  },
  {
   "id": "open-jev-27b::cojevlight",
   "model": "open-jev-27b",
   "mode": "cojevlight",
   "name": "Open JEV 27B",
   "family": "open-jev",
   "family_label": "Open-JEV",
   "color": "#c792ea",
   "kind": "native",
   "hosted": false,
   "params_b": 27.0,
   "score": 92.13,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 319.76,
      "sd": 0.529,
      "score": 99.53
     },
     "awt": {
      "raw": 57.704,
      "sd": 0.166,
      "score": 99.14
     },
     "aql": {
      "raw": 100.65,
      "sd": 0.31,
      "score": 99.02
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.293,
      "sd": 0.384,
      "score": 99.86
     },
     "awt": {
      "raw": 39.021,
      "sd": 0.347,
      "score": 99.61
     },
     "aql": {
      "raw": 47.145,
      "sd": 0.425,
      "score": 99.58
     }
    },
    "jinan-3": {
     "att": {
      "raw": 297.858,
      "sd": 1.118,
      "score": 99.97
     },
     "awt": {
      "raw": 42.89,
      "sd": 0.472,
      "score": 100.0
     },
     "aql": {
      "raw": 65.242,
      "sd": 0.711,
      "score": 100.0
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 341.36,
      "sd": 0.969,
      "score": 100.0
     },
     "awt": {
      "raw": 25.166,
      "sd": 0.203,
      "score": 100.0
     },
     "aql": {
      "raw": 20.786,
      "sd": 0.168,
      "score": 100.0
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 371.497,
      "sd": 1.462,
      "score": 99.71
     },
     "awt": {
      "raw": 65.087,
      "sd": 2.087,
      "score": 99.79
     },
     "aql": {
      "raw": 106.877,
      "sd": 3.448,
      "score": 100.0
     }
    },
    "newyork-1": {
     "att": {
      "raw": 993.675,
      "sd": 2.616,
      "score": 85.8
     },
     "awt": {
      "raw": 553.393,
      "sd": 5.656,
      "score": 80.85
     },
     "aql": {
      "raw": 1444.048,
      "sd": 15.99,
      "score": 72.61
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1351.27,
      "sd": 13.462,
      "score": 73.32
     },
     "awt": {
      "raw": 961.449,
      "sd": 15.225,
      "score": 68.81
     },
     "aql": {
      "raw": 3009.326,
      "sd": 27.287,
      "score": 57.23
     }
    }
   },
   "cost": {
    "gpu_seconds": 13441.2,
    "serving_seconds": 4624.2,
    "wall_seconds": 4768.4,
    "tokens_per_task": null,
    "decisions_per_task": 12622,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 4624.2,
     "jinan-2": 4005.9,
     "jinan-3": 4319.7,
     "hangzhou-1": 4014.8,
     "hangzhou-2": 4718.0,
     "newyork-1": 35326.6,
     "newyork-2": 37079.5
    }
   },
   "rank": 5,
   "pareto": false
  },
  {
   "id": "kev-27b::cojevlight",
   "model": "kev-27b",
   "mode": "cojevlight",
   "name": "Kev 27B",
   "family": "kev",
   "family_label": "Kev",
   "color": "#ffc531",
   "kind": "native",
   "hosted": false,
   "params_b": 27.0,
   "score": 91.96,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 318.341,
      "sd": 1.798,
      "score": 99.82
     },
     "awt": {
      "raw": 56.685,
      "sd": 1.136,
      "score": 99.7
     },
     "aql": {
      "raw": 98.861,
      "sd": 1.976,
      "score": 99.66
     }
    },
    "jinan-2": {
     "att": {
      "raw": 302.95,
      "sd": 0.67,
      "score": 99.93
     },
     "awt": {
      "raw": 38.735,
      "sd": 0.323,
      "score": 99.81
     },
     "aql": {
      "raw": 46.797,
      "sd": 0.378,
      "score": 99.8
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.104,
      "sd": 0.788,
      "score": 99.92
     },
     "awt": {
      "raw": 43.05,
      "sd": 0.237,
      "score": 99.89
     },
     "aql": {
      "raw": 65.5,
      "sd": 0.366,
      "score": 99.87
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 342.508,
      "sd": 0.788,
      "score": 99.78
     },
     "awt": {
      "raw": 25.955,
      "sd": 0.222,
      "score": 99.23
     },
     "aql": {
      "raw": 21.439,
      "sd": 0.184,
      "score": 99.15
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 371.512,
      "sd": 1.745,
      "score": 99.71
     },
     "awt": {
      "raw": 64.729,
      "sd": 1.427,
      "score": 100.0
     },
     "aql": {
      "raw": 107.597,
      "sd": 2.825,
      "score": 99.68
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1004.441,
      "sd": 3.567,
      "score": 84.5
     },
     "awt": {
      "raw": 565.009,
      "sd": 5.748,
      "score": 79.48
     },
     "aql": {
      "raw": 1468.945,
      "sd": 11.431,
      "score": 71.18
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1348.381,
      "sd": 12.603,
      "score": 73.66
     },
     "awt": {
      "raw": 956.605,
      "sd": 17.361,
      "score": 69.29
     },
     "aql": {
      "raw": 3012.266,
      "sd": 43.338,
      "score": 57.1
     }
    }
   },
   "cost": {
    "gpu_seconds": 6320.5,
    "serving_seconds": 2101.3,
    "wall_seconds": 18615.5,
    "tokens_per_task": 27061092,
    "decisions_per_task": 12643,
    "tokens_per_decision": 2140.5,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 2101.3,
     "jinan-2": 1828.3,
     "jinan-3": 2018.0,
     "hangzhou-1": 1864.6,
     "hangzhou-2": 2173.4,
     "newyork-1": 16567.4,
     "newyork-2": 17690.5
    }
   },
   "rank": 6,
   "pareto": false
  },
  {
   "id": "open-jev-9b::jevlight",
   "model": "open-jev-9b",
   "mode": "jevlight",
   "name": "Open-Jev 9B",
   "family": "open-jev",
   "family_label": "Open-JEV",
   "color": "#c792ea",
   "kind": "native",
   "hosted": false,
   "params_b": 9.0,
   "score": 91.93,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 332.243,
      "sd": 1.526,
      "score": 97.06
     },
     "awt": {
      "raw": 66.6,
      "sd": 0.861,
      "score": 94.63
     },
     "aql": {
      "raw": 116.072,
      "sd": 1.477,
      "score": 93.93
     }
    },
    "jinan-2": {
     "att": {
      "raw": 307.187,
      "sd": 0.349,
      "score": 99.09
     },
     "awt": {
      "raw": 41.855,
      "sd": 0.683,
      "score": 97.67
     },
     "aql": {
      "raw": 50.585,
      "sd": 0.812,
      "score": 97.49
     }
    },
    "jinan-3": {
     "att": {
      "raw": 306.263,
      "sd": 1.276,
      "score": 98.21
     },
     "awt": {
      "raw": 49.088,
      "sd": 1.196,
      "score": 96.05
     },
     "aql": {
      "raw": 74.702,
      "sd": 1.839,
      "score": 95.63
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 347.508,
      "sd": 0.606,
      "score": 98.81
     },
     "awt": {
      "raw": 29.335,
      "sd": 0.417,
      "score": 96.16
     },
     "aql": {
      "raw": 24.246,
      "sd": 0.342,
      "score": 95.78
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 381.78,
      "sd": 1.025,
      "score": 97.11
     },
     "awt": {
      "raw": 78.943,
      "sd": 0.679,
      "score": 92.46
     },
     "aql": {
      "raw": 132.272,
      "sd": 0.857,
      "score": 89.97
     }
    },
    "newyork-1": {
     "att": {
      "raw": 944.64,
      "sd": 5.519,
      "score": 91.93
     },
     "awt": {
      "raw": 487.279,
      "sd": 7.689,
      "score": 89.21
     },
     "aql": {
      "raw": 1256.505,
      "sd": 17.522,
      "score": 84.3
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1295.639,
      "sd": 11.346,
      "score": 80.03
     },
     "awt": {
      "raw": 876.233,
      "sd": 14.575,
      "score": 77.47
     },
     "aql": {
      "raw": 2780.853,
      "sd": 44.035,
      "score": 67.56
     }
    }
   },
   "cost": {
    "gpu_seconds": 3236.3,
    "serving_seconds": 928.3,
    "wall_seconds": null,
    "tokens_per_task": null,
    "decisions_per_task": 12857,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 718.6,
     "jinan-2": 732.4,
     "jinan-3": 717.5,
     "hangzhou-1": 939.9,
     "hangzhou-2": 930.0,
     "newyork-1": 9297.9,
     "newyork-2": 9318.0
    }
   },
   "rank": 7,
   "pareto": false
  },
  {
   "id": "d3::cojevlight",
   "model": "d3",
   "mode": "cojevlight",
   "name": "D3",
   "family": "d3",
   "family_label": "D3",
   "color": "#4dd0e1",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 91.91,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 319.692,
      "sd": 1.086,
      "score": 99.54
     },
     "awt": {
      "raw": 57.529,
      "sd": 0.814,
      "score": 99.23
     },
     "aql": {
      "raw": 100.343,
      "sd": 1.421,
      "score": 99.13
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.36,
      "sd": 0.6,
      "score": 99.85
     },
     "awt": {
      "raw": 38.762,
      "sd": 0.164,
      "score": 99.79
     },
     "aql": {
      "raw": 46.857,
      "sd": 0.183,
      "score": 99.76
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.726,
      "sd": 0.564,
      "score": 99.79
     },
     "awt": {
      "raw": 43.369,
      "sd": 0.11,
      "score": 99.67
     },
     "aql": {
      "raw": 65.992,
      "sd": 0.175,
      "score": 99.63
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 343.148,
      "sd": 1.083,
      "score": 99.65
     },
     "awt": {
      "raw": 26.349,
      "sd": 0.232,
      "score": 98.85
     },
     "aql": {
      "raw": 21.774,
      "sd": 0.186,
      "score": 98.73
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 370.364,
      "sd": 0.901,
      "score": 100.0
     },
     "awt": {
      "raw": 65.032,
      "sd": 0.72,
      "score": 99.82
     },
     "aql": {
      "raw": 109.485,
      "sd": 1.678,
      "score": 98.87
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1008.188,
      "sd": 8.491,
      "score": 84.05
     },
     "awt": {
      "raw": 573.886,
      "sd": 7.432,
      "score": 78.46
     },
     "aql": {
      "raw": 1499.491,
      "sd": 19.769,
      "score": 69.45
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1329.993,
      "sd": 6.945,
      "score": 75.85
     },
     "awt": {
      "raw": 937.446,
      "sd": 12.953,
      "score": 71.17
     },
     "aql": {
      "raw": 2973.826,
      "sd": 30.162,
      "score": 58.78
     }
    }
   },
   "cost": {
    "gpu_seconds": 13475.2,
    "serving_seconds": 4248.2,
    "wall_seconds": 4394.7,
    "tokens_per_task": 27201359,
    "decisions_per_task": 12693,
    "tokens_per_decision": 2143.0,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 4248.2,
     "jinan-2": 3627.2,
     "jinan-3": 3979.6,
     "hangzhou-1": 3685.1,
     "hangzhou-2": 4297.5,
     "newyork-1": 32426.0,
     "newyork-2": 42063.1
    }
   },
   "rank": 8,
   "pareto": false
  },
  {
   "id": "clef-27b::cojevlight",
   "model": "clef-27b",
   "mode": "cojevlight",
   "name": "Clef 27B",
   "family": "clef",
   "family_label": "Clef",
   "color": "#ff8a65",
   "kind": "native",
   "hosted": false,
   "params_b": 27.0,
   "score": 90.85,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 317.435,
      "sd": 0.773,
      "score": 100.0
     },
     "awt": {
      "raw": 56.147,
      "sd": 0.529,
      "score": 100.0
     },
     "aql": {
      "raw": 97.912,
      "sd": 0.955,
      "score": 100.0
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.227,
      "sd": 0.969,
      "score": 99.87
     },
     "awt": {
      "raw": 39.198,
      "sd": 0.533,
      "score": 99.48
     },
     "aql": {
      "raw": 47.376,
      "sd": 0.631,
      "score": 99.43
     }
    },
    "jinan-3": {
     "att": {
      "raw": 297.743,
      "sd": 1.105,
      "score": 99.99
     },
     "awt": {
      "raw": 43.037,
      "sd": 0.537,
      "score": 99.9
     },
     "aql": {
      "raw": 65.479,
      "sd": 0.807,
      "score": 99.88
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 343.153,
      "sd": 1.397,
      "score": 99.65
     },
     "awt": {
      "raw": 26.97,
      "sd": 0.54,
      "score": 98.27
     },
     "aql": {
      "raw": 22.288,
      "sd": 0.445,
      "score": 98.09
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 375.496,
      "sd": 1.531,
      "score": 98.69
     },
     "awt": {
      "raw": 69.668,
      "sd": 1.148,
      "score": 97.21
     },
     "aql": {
      "raw": 117.901,
      "sd": 2.094,
      "score": 95.38
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1021.672,
      "sd": 2.601,
      "score": 82.44
     },
     "awt": {
      "raw": 590.751,
      "sd": 3.492,
      "score": 76.55
     },
     "aql": {
      "raw": 1539.821,
      "sd": 2.682,
      "score": 67.22
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1358.262,
      "sd": 6.235,
      "score": 72.5
     },
     "awt": {
      "raw": 968.273,
      "sd": 5.229,
      "score": 68.16
     },
     "aql": {
      "raw": 3058.081,
      "sd": 13.035,
      "score": 55.13
     }
    }
   },
   "cost": {
    "gpu_seconds": 5780.3,
    "serving_seconds": 1837.1,
    "wall_seconds": 1973.6,
    "tokens_per_task": 24132138,
    "decisions_per_task": 12674,
    "tokens_per_decision": 1904.1,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1837.1,
     "jinan-2": 1622.1,
     "jinan-3": 1756.5,
     "hangzhou-1": 1700.7,
     "hangzhou-2": 1990.7,
     "newyork-1": 15377.3,
     "newyork-2": 16177.4
    }
   },
   "rank": 9,
   "pareto": false
  },
  {
   "id": "open-jev-9b::cojevlight",
   "model": "open-jev-9b",
   "mode": "cojevlight",
   "name": "Open-Jev 9B",
   "family": "open-jev",
   "family_label": "Open-JEV",
   "color": "#c792ea",
   "kind": "native",
   "hosted": false,
   "params_b": 9.0,
   "score": 90.41,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 320.943,
      "sd": 0.859,
      "score": 99.29
     },
     "awt": {
      "raw": 60.539,
      "sd": 0.365,
      "score": 97.63
     },
     "aql": {
      "raw": 105.605,
      "sd": 0.66,
      "score": 97.3
     }
    },
    "jinan-2": {
     "att": {
      "raw": 309.005,
      "sd": 0.764,
      "score": 98.74
     },
     "awt": {
      "raw": 45.271,
      "sd": 0.265,
      "score": 95.5
     },
     "aql": {
      "raw": 54.736,
      "sd": 0.312,
      "score": 95.15
     }
    },
    "jinan-3": {
     "att": {
      "raw": 301.097,
      "sd": 1.091,
      "score": 99.29
     },
     "awt": {
      "raw": 47.157,
      "sd": 0.702,
      "score": 97.22
     },
     "aql": {
      "raw": 71.766,
      "sd": 1.078,
      "score": 96.93
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 346.104,
      "sd": 0.526,
      "score": 99.08
     },
     "awt": {
      "raw": 29.963,
      "sd": 0.574,
      "score": 95.63
     },
     "aql": {
      "raw": 24.765,
      "sd": 0.475,
      "score": 95.2
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 372.804,
      "sd": 1.342,
      "score": 99.38
     },
     "awt": {
      "raw": 68.876,
      "sd": 2.083,
      "score": 97.64
     },
     "aql": {
      "raw": 115.351,
      "sd": 3.995,
      "score": 96.41
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1024.983,
      "sd": 9.264,
      "score": 82.05
     },
     "awt": {
      "raw": 604.902,
      "sd": 13.87,
      "score": 75.0
     },
     "aql": {
      "raw": 1556.877,
      "sd": 36.202,
      "score": 66.3
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1311.819,
      "sd": 14.375,
      "score": 78.05
     },
     "awt": {
      "raw": 906.857,
      "sd": 16.027,
      "score": 74.27
     },
     "aql": {
      "raw": 2887.906,
      "sd": 44.853,
      "score": 62.62
     }
    }
   },
   "cost": {
    "gpu_seconds": 8470.1,
    "serving_seconds": 2872.9,
    "wall_seconds": null,
    "tokens_per_task": null,
    "decisions_per_task": 12678,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 2910.6,
     "jinan-2": 2557.0,
     "jinan-3": 2769.9,
     "hangzhou-1": 2516.0,
     "hangzhou-2": 2957.5,
     "newyork-1": 22032.3,
     "newyork-2": 23547.1
    }
   },
   "rank": 10,
   "pareto": false
  },
  {
   "id": "lev::cojevlight",
   "model": "lev",
   "mode": "cojevlight",
   "name": "Lev",
   "family": "lev",
   "family_label": "Lev",
   "color": "#90a4ae",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 90.07,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 318.603,
      "sd": 0.728,
      "score": 99.76
     },
     "awt": {
      "raw": 57.821,
      "sd": 0.264,
      "score": 99.08
     },
     "aql": {
      "raw": 100.854,
      "sd": 0.455,
      "score": 98.94
     }
    },
    "jinan-2": {
     "att": {
      "raw": 307.219,
      "sd": 1.013,
      "score": 99.09
     },
     "awt": {
      "raw": 43.22,
      "sd": 0.359,
      "score": 96.78
     },
     "aql": {
      "raw": 52.245,
      "sd": 0.419,
      "score": 96.53
     }
    },
    "jinan-3": {
     "att": {
      "raw": 301.221,
      "sd": 0.507,
      "score": 99.26
     },
     "awt": {
      "raw": 46.551,
      "sd": 0.191,
      "score": 97.6
     },
     "aql": {
      "raw": 70.833,
      "sd": 0.307,
      "score": 97.35
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 344.727,
      "sd": 1.129,
      "score": 99.35
     },
     "awt": {
      "raw": 28.761,
      "sd": 0.289,
      "score": 96.66
     },
     "aql": {
      "raw": 23.775,
      "sd": 0.24,
      "score": 96.32
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 370.365,
      "sd": 2.011,
      "score": 100.0
     },
     "awt": {
      "raw": 66.187,
      "sd": 1.171,
      "score": 99.15
     },
     "aql": {
      "raw": 109.448,
      "sd": 2.073,
      "score": 98.88
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1043.936,
      "sd": 13.317,
      "score": 79.83
     },
     "awt": {
      "raw": 614.344,
      "sd": 16.976,
      "score": 73.98
     },
     "aql": {
      "raw": 1605.134,
      "sd": 43.57,
      "score": 63.74
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1345.129,
      "sd": 13.827,
      "score": 74.05
     },
     "awt": {
      "raw": 949.74,
      "sd": 20.172,
      "score": 69.96
     },
     "aql": {
      "raw": 3056.051,
      "sd": 49.897,
      "score": 55.22
     }
    }
   },
   "cost": {
    "gpu_seconds": 3645.1,
    "serving_seconds": 1188.6,
    "wall_seconds": null,
    "tokens_per_task": 35276321,
    "decisions_per_task": 12498,
    "tokens_per_decision": 2822.5,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1188.6,
     "jinan-2": 1058.6,
     "jinan-3": 1174.7,
     "hangzhou-1": 1073.5,
     "hangzhou-2": 1278.9,
     "newyork-1": 9430.0,
     "newyork-2": 10311.7
    }
   },
   "rank": 11,
   "pareto": false
  },
  {
   "id": "pplx-decider-v1.2::jevlight",
   "model": "pplx-decider-v1.2",
   "mode": "jevlight",
   "name": "PPLX Decider v1.2",
   "family": "pplx",
   "family_label": "PPLX",
   "color": "#f06292",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 89.91,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 322.417,
      "sd": 1.931,
      "score": 99.0
     },
     "awt": {
      "raw": 59.809,
      "sd": 1.185,
      "score": 98.01
     },
     "aql": {
      "raw": 104.345,
      "sd": 2.078,
      "score": 97.73
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.256,
      "sd": 0.873,
      "score": 99.87
     },
     "awt": {
      "raw": 38.553,
      "sd": 0.548,
      "score": 99.94
     },
     "aql": {
      "raw": 46.581,
      "sd": 0.66,
      "score": 99.94
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.651,
      "sd": 0.917,
      "score": 99.8
     },
     "awt": {
      "raw": 43.225,
      "sd": 0.327,
      "score": 99.77
     },
     "aql": {
      "raw": 65.755,
      "sd": 0.505,
      "score": 99.75
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 345.092,
      "sd": 1.168,
      "score": 99.28
     },
     "awt": {
      "raw": 26.535,
      "sd": 0.335,
      "score": 98.67
     },
     "aql": {
      "raw": 21.91,
      "sd": 0.287,
      "score": 98.56
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 384.261,
      "sd": 1.027,
      "score": 96.5
     },
     "awt": {
      "raw": 68.292,
      "sd": 0.687,
      "score": 97.96
     },
     "aql": {
      "raw": 110.232,
      "sd": 1.338,
      "score": 98.55
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1083.15,
      "sd": 5.674,
      "score": 75.37
     },
     "awt": {
      "raw": 625.254,
      "sd": 9.823,
      "score": 72.82
     },
     "aql": {
      "raw": 1558.666,
      "sd": 25.341,
      "score": 66.2
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1407.882,
      "sd": 3.781,
      "score": 66.78
     },
     "awt": {
      "raw": 982.98,
      "sd": 5.239,
      "score": 66.75
     },
     "aql": {
      "raw": 3018.781,
      "sd": 15.631,
      "score": 56.82
     }
    }
   },
   "cost": {
    "gpu_seconds": 4608.4,
    "serving_seconds": 1324.9,
    "wall_seconds": 1446.9,
    "tokens_per_task": 11376932,
    "decisions_per_task": 12779,
    "tokens_per_decision": 890.3,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1050.8,
     "jinan-2": 1065.9,
     "jinan-3": 1046.8,
     "hangzhou-1": 1352.3,
     "hangzhou-2": 1328.0,
     "newyork-1": 13003.7,
     "newyork-2": 13411.0
    }
   },
   "rank": 12,
   "pareto": false
  },
  {
   "id": "pplx-decider-v1.2::cojevlight",
   "model": "pplx-decider-v1.2",
   "mode": "cojevlight",
   "name": "PPLX Decider v1.2",
   "family": "pplx",
   "family_label": "PPLX",
   "color": "#f06292",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 89.8,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 320.709,
      "sd": 0.59,
      "score": 99.34
     },
     "awt": {
      "raw": 58.424,
      "sd": 0.137,
      "score": 98.75
     },
     "aql": {
      "raw": 101.916,
      "sd": 0.253,
      "score": 98.57
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.181,
      "sd": 0.783,
      "score": 99.88
     },
     "awt": {
      "raw": 38.576,
      "sd": 0.282,
      "score": 99.92
     },
     "aql": {
      "raw": 46.614,
      "sd": 0.342,
      "score": 99.91
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.255,
      "sd": 0.781,
      "score": 99.89
     },
     "awt": {
      "raw": 42.971,
      "sd": 0.353,
      "score": 99.94
     },
     "aql": {
      "raw": 65.376,
      "sd": 0.522,
      "score": 99.93
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 342.844,
      "sd": 0.718,
      "score": 99.71
     },
     "awt": {
      "raw": 26.025,
      "sd": 0.115,
      "score": 99.16
     },
     "aql": {
      "raw": 21.508,
      "sd": 0.089,
      "score": 99.06
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 371.771,
      "sd": 1.418,
      "score": 99.64
     },
     "awt": {
      "raw": 66.659,
      "sd": 1.43,
      "score": 98.88
     },
     "aql": {
      "raw": 112.693,
      "sd": 2.412,
      "score": 97.51
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1063.475,
      "sd": 4.558,
      "score": 77.59
     },
     "awt": {
      "raw": 654.307,
      "sd": 5.956,
      "score": 69.83
     },
     "aql": {
      "raw": 1707.323,
      "sd": 4.789,
      "score": 58.55
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1369.988,
      "sd": 4.763,
      "score": 71.13
     },
     "awt": {
      "raw": 990.911,
      "sd": 6.146,
      "score": 66.0
     },
     "aql": {
      "raw": 3120.404,
      "sd": 9.204,
      "score": 52.49
     }
    }
   },
   "cost": {
    "gpu_seconds": 12302.4,
    "serving_seconds": 4242.1,
    "wall_seconds": 4382.0,
    "tokens_per_task": 27041853,
    "decisions_per_task": 12647,
    "tokens_per_decision": 2138.1,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 4242.1,
     "jinan-2": 3639.5,
     "jinan-3": 3956.5,
     "hangzhou-1": 3667.1,
     "hangzhou-2": 4383.3,
     "newyork-1": 32209.1,
     "newyork-2": 34019.3
    }
   },
   "rank": 13,
   "pareto": false
  },
  {
   "id": "startlux-9b::jevlight",
   "model": "startlux-9b",
   "mode": "jevlight",
   "name": "StartLux 9B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 9.0,
   "score": 89.73,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 323.048,
      "sd": 0.92,
      "score": 98.87
     },
     "awt": {
      "raw": 60.137,
      "sd": 0.232,
      "score": 97.84
     },
     "aql": {
      "raw": 104.884,
      "sd": 0.412,
      "score": 97.55
     }
    },
    "jinan-2": {
     "att": {
      "raw": 304.33,
      "sd": 1.064,
      "score": 99.66
     },
     "awt": {
      "raw": 39.425,
      "sd": 0.353,
      "score": 99.32
     },
     "aql": {
      "raw": 47.647,
      "sd": 0.422,
      "score": 99.26
     }
    },
    "jinan-3": {
     "att": {
      "raw": 300.35,
      "sd": 0.986,
      "score": 99.44
     },
     "awt": {
      "raw": 44.521,
      "sd": 0.428,
      "score": 98.91
     },
     "aql": {
      "raw": 67.744,
      "sd": 0.652,
      "score": 98.79
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 343.997,
      "sd": 1.093,
      "score": 99.49
     },
     "awt": {
      "raw": 26.505,
      "sd": 0.296,
      "score": 98.7
     },
     "aql": {
      "raw": 21.893,
      "sd": 0.243,
      "score": 98.58
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 379.811,
      "sd": 2.416,
      "score": 97.6
     },
     "awt": {
      "raw": 70.189,
      "sd": 1.556,
      "score": 96.92
     },
     "aql": {
      "raw": 117.826,
      "sd": 2.938,
      "score": 95.41
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1037.984,
      "sd": 4.442,
      "score": 80.53
     },
     "awt": {
      "raw": 591.656,
      "sd": 6.206,
      "score": 76.45
     },
     "aql": {
      "raw": 1532.575,
      "sd": 15.113,
      "score": 67.62
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1403.264,
      "sd": 5.052,
      "score": 67.3
     },
     "awt": {
      "raw": 1008.677,
      "sd": 7.329,
      "score": 64.34
     },
     "aql": {
      "raw": 3139.513,
      "sd": 29.099,
      "score": 51.69
     }
    }
   },
   "cost": {
    "gpu_seconds": 736.4,
    "serving_seconds": 298.8,
    "wall_seconds": 393.9,
    "tokens_per_task": 11173468,
    "decisions_per_task": 12722,
    "tokens_per_decision": 878.3,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 230.7,
     "jinan-2": 230.9,
     "jinan-3": 230.7,
     "hangzhou-1": 299.2,
     "hangzhou-2": 298.8,
     "newyork-1": 2976.6,
     "newyork-2": 887.8
    }
   },
   "rank": 14,
   "pareto": true
  },
  {
   "id": "pplx-decider-flash-v1.2::jevlight",
   "model": "pplx-decider-flash-v1.2",
   "mode": "jevlight",
   "name": "PPLX Decider Flash v1.2",
   "family": "pplx",
   "family_label": "PPLX",
   "color": "#f06292",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 89.56,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 321.308,
      "sd": 0.843,
      "score": 99.22
     },
     "awt": {
      "raw": 58.945,
      "sd": 0.32,
      "score": 98.47
     },
     "aql": {
      "raw": 102.798,
      "sd": 0.562,
      "score": 98.26
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.767,
      "sd": 0.68,
      "score": 99.77
     },
     "awt": {
      "raw": 39.192,
      "sd": 0.307,
      "score": 99.49
     },
     "aql": {
      "raw": 47.377,
      "sd": 0.354,
      "score": 99.43
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.636,
      "sd": 0.716,
      "score": 99.8
     },
     "awt": {
      "raw": 43.129,
      "sd": 0.389,
      "score": 99.84
     },
     "aql": {
      "raw": 65.613,
      "sd": 0.584,
      "score": 99.82
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 346.796,
      "sd": 1.605,
      "score": 98.95
     },
     "awt": {
      "raw": 27.81,
      "sd": 0.42,
      "score": 97.5
     },
     "aql": {
      "raw": 22.981,
      "sd": 0.335,
      "score": 97.25
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 382.846,
      "sd": 1.832,
      "score": 96.85
     },
     "awt": {
      "raw": 69.306,
      "sd": 2.114,
      "score": 97.41
     },
     "aql": {
      "raw": 111.89,
      "sd": 3.198,
      "score": 97.84
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1086.001,
      "sd": 1.186,
      "score": 75.05
     },
     "awt": {
      "raw": 651.14,
      "sd": 2.565,
      "score": 70.15
     },
     "aql": {
      "raw": 1633.36,
      "sd": 7.331,
      "score": 62.27
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1387.255,
      "sd": 2.984,
      "score": 69.13
     },
     "awt": {
      "raw": 969.118,
      "sd": 8.074,
      "score": 68.07
     },
     "aql": {
      "raw": 3031.349,
      "sd": 29.688,
      "score": 56.28
     }
    }
   },
   "cost": {
    "gpu_seconds": 1208.1,
    "serving_seconds": 362.3,
    "wall_seconds": 457.9,
    "tokens_per_task": 11405443,
    "decisions_per_task": 12810,
    "tokens_per_decision": 890.3,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 284.9,
     "jinan-2": 282.8,
     "jinan-3": 284.6,
     "hangzhou-1": 362.3,
     "hangzhou-2": 364.5,
     "newyork-1": 3459.0,
     "newyork-2": 3418.5
    }
   },
   "rank": 15,
   "pareto": false
  },
  {
   "id": "d3::jevlight",
   "model": "d3",
   "mode": "jevlight",
   "name": "D3",
   "family": "d3",
   "family_label": "D3",
   "color": "#4dd0e1",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 89.53,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 322.514,
      "sd": 0.179,
      "score": 98.98
     },
     "awt": {
      "raw": 59.688,
      "sd": 0.522,
      "score": 98.08
     },
     "aql": {
      "raw": 104.113,
      "sd": 0.922,
      "score": 97.81
     }
    },
    "jinan-2": {
     "att": {
      "raw": 303.538,
      "sd": 0.882,
      "score": 99.81
     },
     "awt": {
      "raw": 38.795,
      "sd": 0.305,
      "score": 99.77
     },
     "aql": {
      "raw": 46.882,
      "sd": 0.378,
      "score": 99.74
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.981,
      "sd": 0.924,
      "score": 99.73
     },
     "awt": {
      "raw": 43.398,
      "sd": 0.384,
      "score": 99.66
     },
     "aql": {
      "raw": 66.017,
      "sd": 0.579,
      "score": 99.62
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 344.925,
      "sd": 1.081,
      "score": 99.31
     },
     "awt": {
      "raw": 26.304,
      "sd": 0.281,
      "score": 98.89
     },
     "aql": {
      "raw": 21.721,
      "sd": 0.237,
      "score": 98.79
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 386.396,
      "sd": 2.364,
      "score": 95.97
     },
     "awt": {
      "raw": 69.904,
      "sd": 1.045,
      "score": 97.08
     },
     "aql": {
      "raw": 112.363,
      "sd": 1.738,
      "score": 97.65
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1093.082,
      "sd": 5.04,
      "score": 74.27
     },
     "awt": {
      "raw": 648.23,
      "sd": 10.966,
      "score": 70.45
     },
     "aql": {
      "raw": 1624.425,
      "sd": 29.619,
      "score": 62.73
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1402.066,
      "sd": 10.09,
      "score": 67.44
     },
     "awt": {
      "raw": 979.312,
      "sd": 13.158,
      "score": 67.1
     },
     "aql": {
      "raw": 3007.938,
      "sd": 32.137,
      "score": 57.29
     }
    }
   },
   "cost": {
    "gpu_seconds": 4639.3,
    "serving_seconds": 1341.8,
    "wall_seconds": 1467.9,
    "tokens_per_task": 11484983,
    "decisions_per_task": 12787,
    "tokens_per_decision": 898.2,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1080.0,
     "jinan-2": 1065.3,
     "jinan-3": 1043.0,
     "hangzhou-1": 1371.3,
     "hangzhou-2": 1350.4,
     "newyork-1": 13302.5,
     "newyork-2": 13262.4
    }
   },
   "rank": 16,
   "pareto": false
  },
  {
   "id": "startlux-27b::jevlight",
   "model": "startlux-27b",
   "mode": "jevlight",
   "name": "StartLux 27B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 27.0,
   "score": 89.29,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 322.617,
      "sd": 1.131,
      "score": 98.96
     },
     "awt": {
      "raw": 59.776,
      "sd": 0.805,
      "score": 98.03
     },
     "aql": {
      "raw": 104.283,
      "sd": 1.377,
      "score": 97.75
     }
    },
    "jinan-2": {
     "att": {
      "raw": 304.284,
      "sd": 1.068,
      "score": 99.66
     },
     "awt": {
      "raw": 39.75,
      "sd": 0.456,
      "score": 99.09
     },
     "aql": {
      "raw": 48.038,
      "sd": 0.552,
      "score": 99.02
     }
    },
    "jinan-3": {
     "att": {
      "raw": 300.098,
      "sd": 1.142,
      "score": 99.5
     },
     "awt": {
      "raw": 44.604,
      "sd": 0.704,
      "score": 98.85
     },
     "aql": {
      "raw": 67.86,
      "sd": 1.067,
      "score": 98.73
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 347.525,
      "sd": 1.748,
      "score": 98.81
     },
     "awt": {
      "raw": 28.651,
      "sd": 0.482,
      "score": 96.75
     },
     "aql": {
      "raw": 23.677,
      "sd": 0.401,
      "score": 96.43
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 387.384,
      "sd": 2.797,
      "score": 95.73
     },
     "awt": {
      "raw": 69.217,
      "sd": 1.22,
      "score": 97.45
     },
     "aql": {
      "raw": 110.724,
      "sd": 1.727,
      "score": 98.34
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1085.943,
      "sd": 11.194,
      "score": 75.06
     },
     "awt": {
      "raw": 639.531,
      "sd": 22.558,
      "score": 71.34
     },
     "aql": {
      "raw": 1595.504,
      "sd": 64.538,
      "score": 64.24
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1404.916,
      "sd": 3.616,
      "score": 67.11
     },
     "awt": {
      "raw": 986.18,
      "sd": 5.053,
      "score": 66.45
     },
     "aql": {
      "raw": 2997.601,
      "sd": 25.718,
      "score": 57.74
     }
    }
   },
   "cost": {
    "gpu_seconds": 3607.2,
    "serving_seconds": 268.5,
    "wall_seconds": 396.8,
    "tokens_per_task": 11203092,
    "decisions_per_task": 12757,
    "tokens_per_decision": 878.2,
    "gpus": 4,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1036.7,
     "jinan-2": 1038.2,
     "jinan-3": 849.2,
     "hangzhou-1": 1073.8,
     "hangzhou-2": 1340.2,
     "newyork-1": 9861.0,
     "newyork-2": 10051.2
    }
   },
   "rank": 17,
   "pareto": false
  },
  {
   "id": "d3-flash::jevlight",
   "model": "d3-flash",
   "mode": "jevlight",
   "name": "D3 Flash",
   "family": "d3",
   "family_label": "D3",
   "color": "#4dd0e1",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 88.93,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 321.23,
      "sd": 1.467,
      "score": 99.23
     },
     "awt": {
      "raw": 58.715,
      "sd": 0.994,
      "score": 98.59
     },
     "aql": {
      "raw": 102.425,
      "sd": 1.749,
      "score": 98.39
     }
    },
    "jinan-2": {
     "att": {
      "raw": 304.363,
      "sd": 0.531,
      "score": 99.65
     },
     "awt": {
      "raw": 39.389,
      "sd": 0.131,
      "score": 99.35
     },
     "aql": {
      "raw": 47.6,
      "sd": 0.162,
      "score": 99.29
     }
    },
    "jinan-3": {
     "att": {
      "raw": 299.085,
      "sd": 1.028,
      "score": 99.71
     },
     "awt": {
      "raw": 43.393,
      "sd": 0.405,
      "score": 99.66
     },
     "aql": {
      "raw": 66.01,
      "sd": 0.624,
      "score": 99.62
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 344.346,
      "sd": 0.842,
      "score": 99.42
     },
     "awt": {
      "raw": 26.412,
      "sd": 0.154,
      "score": 98.79
     },
     "aql": {
      "raw": 21.828,
      "sd": 0.125,
      "score": 98.66
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 380.818,
      "sd": 0.339,
      "score": 97.35
     },
     "awt": {
      "raw": 68.199,
      "sd": 1.219,
      "score": 98.02
     },
     "aql": {
      "raw": 111.957,
      "sd": 1.945,
      "score": 97.82
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1102.495,
      "sd": 7.584,
      "score": 73.23
     },
     "awt": {
      "raw": 664.167,
      "sd": 3.615,
      "score": 68.85
     },
     "aql": {
      "raw": 1674.11,
      "sd": 9.824,
      "score": 60.2
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1419.485,
      "sd": 13.297,
      "score": 65.47
     },
     "awt": {
      "raw": 1008.427,
      "sd": 15.837,
      "score": 64.37
     },
     "aql": {
      "raw": 3134.616,
      "sd": 33.1,
      "score": 51.9
     }
    }
   },
   "cost": {
    "gpu_seconds": 1501.5,
    "serving_seconds": 439.6,
    "wall_seconds": 535.2,
    "tokens_per_task": 11442647,
    "decisions_per_task": 12738,
    "tokens_per_decision": 898.3,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 346.8,
     "jinan-2": 349.5,
     "jinan-3": 346.3,
     "hangzhou-1": 440.0,
     "hangzhou-2": 439.9,
     "newyork-1": 4246.9,
     "newyork-2": 4341.0
    }
   },
   "rank": 18,
   "pareto": false
  },
  {
   "id": "startlux-4b::jevlight",
   "model": "startlux-4b",
   "mode": "jevlight",
   "name": "StartLux 4B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 4.0,
   "score": 88.75,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 323.584,
      "sd": 1.068,
      "score": 98.76
     },
     "awt": {
      "raw": 60.233,
      "sd": 0.518,
      "score": 97.79
     },
     "aql": {
      "raw": 105.059,
      "sd": 0.906,
      "score": 97.49
     }
    },
    "jinan-2": {
     "att": {
      "raw": 304.402,
      "sd": 0.859,
      "score": 99.64
     },
     "awt": {
      "raw": 39.608,
      "sd": 0.168,
      "score": 99.19
     },
     "aql": {
      "raw": 47.866,
      "sd": 0.204,
      "score": 99.13
     }
    },
    "jinan-3": {
     "att": {
      "raw": 299.66,
      "sd": 1.426,
      "score": 99.59
     },
     "awt": {
      "raw": 44.062,
      "sd": 0.965,
      "score": 99.21
     },
     "aql": {
      "raw": 67.026,
      "sd": 1.472,
      "score": 99.13
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 346.388,
      "sd": 1.864,
      "score": 99.03
     },
     "awt": {
      "raw": 27.614,
      "sd": 0.88,
      "score": 97.68
     },
     "aql": {
      "raw": 22.825,
      "sd": 0.723,
      "score": 97.44
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 383.597,
      "sd": 0.675,
      "score": 96.66
     },
     "awt": {
      "raw": 68.247,
      "sd": 1.699,
      "score": 97.99
     },
     "aql": {
      "raw": 108.29,
      "sd": 2.566,
      "score": 99.38
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1087.117,
      "sd": 4.496,
      "score": 74.93
     },
     "awt": {
      "raw": 650.223,
      "sd": 4.806,
      "score": 70.25
     },
     "aql": {
      "raw": 1626.269,
      "sd": 8.717,
      "score": 62.64
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1423.817,
      "sd": 7.795,
      "score": 64.98
     },
     "awt": {
      "raw": 1038.38,
      "sd": 13.892,
      "score": 61.64
     },
     "aql": {
      "raw": 3149.694,
      "sd": 37.201,
      "score": 51.27
     }
    }
   },
   "cost": {
    "gpu_seconds": 566.8,
    "serving_seconds": 172.3,
    "wall_seconds": 272.1,
    "tokens_per_task": 11195259,
    "decisions_per_task": 12748,
    "tokens_per_decision": 878.2,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 125.6,
     "jinan-2": 125.8,
     "jinan-3": 124.9,
     "hangzhou-1": 175.1,
     "hangzhou-2": 172.8,
     "newyork-1": 1603.2,
     "newyork-2": 1640.2
    }
   },
   "rank": 19,
   "pareto": true
  },
  {
   "id": "startlux-27b::cojevlight",
   "model": "startlux-27b",
   "mode": "cojevlight",
   "name": "StartLux 27B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 27.0,
   "score": 88.62,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 327.046,
      "sd": 0.572,
      "score": 98.08
     },
     "awt": {
      "raw": 63.801,
      "sd": 0.77,
      "score": 95.98
     },
     "aql": {
      "raw": 111.317,
      "sd": 1.347,
      "score": 95.42
     }
    },
    "jinan-2": {
     "att": {
      "raw": 306.411,
      "sd": 1.117,
      "score": 99.24
     },
     "awt": {
      "raw": 41.59,
      "sd": 0.382,
      "score": 97.84
     },
     "aql": {
      "raw": 50.278,
      "sd": 0.467,
      "score": 97.67
     }
    },
    "jinan-3": {
     "att": {
      "raw": 305.078,
      "sd": 1.62,
      "score": 98.46
     },
     "awt": {
      "raw": 48.924,
      "sd": 0.902,
      "score": 96.15
     },
     "aql": {
      "raw": 74.456,
      "sd": 1.379,
      "score": 95.74
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 346.084,
      "sd": 1.593,
      "score": 99.09
     },
     "awt": {
      "raw": 28.573,
      "sd": 0.774,
      "score": 96.82
     },
     "aql": {
      "raw": 23.619,
      "sd": 0.638,
      "score": 96.5
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 377.923,
      "sd": 3.809,
      "score": 98.08
     },
     "awt": {
      "raw": 68.608,
      "sd": 3.431,
      "score": 97.79
     },
     "aql": {
      "raw": 113.134,
      "sd": 5.693,
      "score": 97.32
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1077.431,
      "sd": 6.375,
      "score": 76.01
     },
     "awt": {
      "raw": 683.148,
      "sd": 8.203,
      "score": 67.0
     },
     "aql": {
      "raw": 1724.995,
      "sd": 22.778,
      "score": 57.69
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1346.142,
      "sd": 14.652,
      "score": 73.93
     },
     "awt": {
      "raw": 971.522,
      "sd": 17.468,
      "score": 67.84
     },
     "aql": {
      "raw": 2982.731,
      "sd": 39.912,
      "score": 58.39
     }
    }
   },
   "cost": {
    "gpu_seconds": 9507.2,
    "serving_seconds": 743.5,
    "wall_seconds": 884.8,
    "tokens_per_task": 26832361,
    "decisions_per_task": 12736,
    "tokens_per_decision": 2106.9,
    "gpus": 4,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 2974.1,
     "jinan-2": 2702.7,
     "jinan-3": 2870.2,
     "hangzhou-1": 2833.0,
     "hangzhou-2": 3154.0,
     "newyork-1": 25318.4,
     "newyork-2": 26697.9
    }
   },
   "rank": 20,
   "pareto": false
  },
  {
   "id": "open-jev-27b::jevlight",
   "model": "open-jev-27b",
   "mode": "jevlight",
   "name": "Open JEV 27B",
   "family": "open-jev",
   "family_label": "Open-JEV",
   "color": "#c792ea",
   "kind": "native",
   "hosted": false,
   "params_b": 27.0,
   "score": 88.58,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 318.74,
      "sd": 1.328,
      "score": 99.74
     },
     "awt": {
      "raw": 57.53,
      "sd": 0.658,
      "score": 99.23
     },
     "aql": {
      "raw": 100.335,
      "sd": 1.143,
      "score": 99.13
     }
    },
    "jinan-2": {
     "att": {
      "raw": 304.181,
      "sd": 0.428,
      "score": 99.68
     },
     "awt": {
      "raw": 39.479,
      "sd": 0.226,
      "score": 99.28
     },
     "aql": {
      "raw": 47.712,
      "sd": 0.254,
      "score": 99.22
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.801,
      "sd": 0.38,
      "score": 99.77
     },
     "awt": {
      "raw": 43.518,
      "sd": 0.276,
      "score": 99.57
     },
     "aql": {
      "raw": 66.2,
      "sd": 0.41,
      "score": 99.53
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 344.529,
      "sd": 1.607,
      "score": 99.39
     },
     "awt": {
      "raw": 26.85,
      "sd": 0.632,
      "score": 98.38
     },
     "aql": {
      "raw": 22.184,
      "sd": 0.516,
      "score": 98.22
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 378.151,
      "sd": 1.974,
      "score": 98.02
     },
     "awt": {
      "raw": 69.517,
      "sd": 0.853,
      "score": 97.29
     },
     "aql": {
      "raw": 116.736,
      "sd": 1.839,
      "score": 95.85
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1076.47,
      "sd": 5.531,
      "score": 76.12
     },
     "awt": {
      "raw": 647.697,
      "sd": 7.62,
      "score": 70.5
     },
     "aql": {
      "raw": 1696.185,
      "sd": 15.653,
      "score": 59.1
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1427.397,
      "sd": 9.854,
      "score": 64.58
     },
     "awt": {
      "raw": 1033.178,
      "sd": 11.063,
      "score": 62.1
     },
     "aql": {
      "raw": 3293.057,
      "sd": 18.601,
      "score": 45.45
     }
    }
   },
   "cost": {
    "gpu_seconds": 5009.2,
    "serving_seconds": 1476.4,
    "wall_seconds": 1572.2,
    "tokens_per_task": null,
    "decisions_per_task": 12675,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1156.3,
     "jinan-2": 1163.7,
     "jinan-3": 1158.5,
     "hangzhou-1": 1476.4,
     "hangzhou-2": 1478.8,
     "newyork-1": 14231.0,
     "newyork-2": 14399.9
    }
   },
   "rank": 21,
   "pareto": false
  },
  {
   "id": "jev-api::jevlight",
   "model": "jev-api",
   "mode": "jevlight",
   "name": "Jev API",
   "family": "jev-api",
   "family_label": "Jev API",
   "color": "#e8eef5",
   "kind": "api",
   "hosted": true,
   "params_b": null,
   "score": 88.24,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 327.404,
      "sd": 0.363,
      "score": 98.01
     },
     "awt": {
      "raw": 63.733,
      "sd": 0.428,
      "score": 96.01
     },
     "aql": {
      "raw": 111.193,
      "sd": 0.755,
      "score": 95.46
     }
    },
    "jinan-2": {
     "att": {
      "raw": 305.756,
      "sd": 0.289,
      "score": 99.37
     },
     "awt": {
      "raw": 40.643,
      "sd": 0.362,
      "score": 98.48
     },
     "aql": {
      "raw": 49.127,
      "sd": 0.441,
      "score": 98.36
     }
    },
    "jinan-3": {
     "att": {
      "raw": 303.178,
      "sd": 1.303,
      "score": 98.85
     },
     "awt": {
      "raw": 46.882,
      "sd": 0.873,
      "score": 97.39
     },
     "aql": {
      "raw": 71.336,
      "sd": 1.317,
      "score": 97.12
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 345.278,
      "sd": 1.344,
      "score": 99.24
     },
     "awt": {
      "raw": 27.202,
      "sd": 0.567,
      "score": 98.05
     },
     "aql": {
      "raw": 22.483,
      "sd": 0.472,
      "score": 97.85
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 382.12,
      "sd": 0.626,
      "score": 97.03
     },
     "awt": {
      "raw": 71.052,
      "sd": 0.65,
      "score": 96.46
     },
     "aql": {
      "raw": 119.111,
      "sd": 1.374,
      "score": 94.9
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1069.438,
      "sd": 11.923,
      "score": 76.91
     },
     "awt": {
      "raw": 625.313,
      "sd": 15.382,
      "score": 72.81
     },
     "aql": {
      "raw": 1612.894,
      "sd": 29.456,
      "score": 63.33
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1422.744,
      "sd": 4.717,
      "score": 65.1
     },
     "awt": {
      "raw": 1031.554,
      "sd": 3.912,
      "score": 62.25
     },
     "aql": {
      "raw": 3179.011,
      "sd": 11.689,
      "score": 50.06
     }
    }
   },
   "cost": {
    "gpu_seconds": null,
    "serving_seconds": 567.1,
    "wall_seconds": null,
    "tokens_per_task": 15499233,
    "decisions_per_task": 12709,
    "tokens_per_decision": 1219.6,
    "gpus": null,
    "hosted": true,
    "runs": 21,
    "by_flow": {
     "jinan-1": null,
     "jinan-2": null,
     "jinan-3": null,
     "hangzhou-1": null,
     "hangzhou-2": null,
     "newyork-1": null,
     "newyork-2": null
    }
   },
   "rank": 22,
   "pareto": false
  },
  {
   "id": "kev-9b::jevlight",
   "model": "kev-9b",
   "mode": "jevlight",
   "name": "Kev 9B",
   "family": "kev",
   "family_label": "Kev",
   "color": "#ffc531",
   "kind": "native",
   "hosted": false,
   "params_b": 9.0,
   "score": 87.68,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 321.616,
      "sd": 1.038,
      "score": 99.16
     },
     "awt": {
      "raw": 59.511,
      "sd": 0.43,
      "score": 98.17
     },
     "aql": {
      "raw": 103.803,
      "sd": 0.747,
      "score": 97.92
     }
    },
    "jinan-2": {
     "att": {
      "raw": 305.288,
      "sd": 0.884,
      "score": 99.47
     },
     "awt": {
      "raw": 40.358,
      "sd": 0.41,
      "score": 98.67
     },
     "aql": {
      "raw": 48.775,
      "sd": 0.5,
      "score": 98.57
     }
    },
    "jinan-3": {
     "att": {
      "raw": 299.5,
      "sd": 0.719,
      "score": 99.62
     },
     "awt": {
      "raw": 44.073,
      "sd": 0.317,
      "score": 99.2
     },
     "aql": {
      "raw": 67.05,
      "sd": 0.462,
      "score": 99.12
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 344.501,
      "sd": 1.124,
      "score": 99.39
     },
     "awt": {
      "raw": 26.689,
      "sd": 0.392,
      "score": 98.53
     },
     "aql": {
      "raw": 22.055,
      "sd": 0.326,
      "score": 98.38
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 377.327,
      "sd": 0.995,
      "score": 98.23
     },
     "awt": {
      "raw": 68.851,
      "sd": 0.924,
      "score": 97.66
     },
     "aql": {
      "raw": 115.883,
      "sd": 2.001,
      "score": 96.2
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1089.731,
      "sd": 5.743,
      "score": 74.64
     },
     "awt": {
      "raw": 665.891,
      "sd": 9.626,
      "score": 68.68
     },
     "aql": {
      "raw": 1750.201,
      "sd": 21.328,
      "score": 56.47
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1445.207,
      "sd": 6.962,
      "score": 62.6
     },
     "awt": {
      "raw": 1068.669,
      "sd": 5.711,
      "score": 58.95
     },
     "aql": {
      "raw": 3390.863,
      "sd": 8.624,
      "score": 41.62
     }
    }
   },
   "cost": {
    "gpu_seconds": 790.6,
    "serving_seconds": 233.5,
    "wall_seconds": null,
    "tokens_per_task": 11006677,
    "decisions_per_task": 12639,
    "tokens_per_decision": 870.9,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 183.7,
     "jinan-2": 188.6,
     "jinan-3": 184.4,
     "hangzhou-1": 240.6,
     "hangzhou-2": 234.8,
     "newyork-1": 2259.4,
     "newyork-2": 2242.6
    }
   },
   "rank": 23,
   "pareto": false
  },
  {
   "id": "clef-flash::jevlight",
   "model": "clef-flash",
   "mode": "jevlight",
   "name": "Clef Flash",
   "family": "clef",
   "family_label": "Clef",
   "color": "#ff8a65",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 87.24,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 323.472,
      "sd": 1.298,
      "score": 98.78
     },
     "awt": {
      "raw": 63.16,
      "sd": 1.04,
      "score": 96.3
     },
     "aql": {
      "raw": 110.174,
      "sd": 1.811,
      "score": 95.79
     }
    },
    "jinan-2": {
     "att": {
      "raw": 312.712,
      "sd": 0.22,
      "score": 98.02
     },
     "awt": {
      "raw": 48.79,
      "sd": 0.361,
      "score": 93.43
     },
     "aql": {
      "raw": 58.994,
      "sd": 0.445,
      "score": 92.92
     }
    },
    "jinan-3": {
     "att": {
      "raw": 304.34,
      "sd": 0.444,
      "score": 98.61
     },
     "awt": {
      "raw": 50.174,
      "sd": 0.269,
      "score": 95.41
     },
     "aql": {
      "raw": 76.385,
      "sd": 0.423,
      "score": 94.92
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 369.177,
      "sd": 2.191,
      "score": 94.8
     },
     "awt": {
      "raw": 53.896,
      "sd": 1.515,
      "score": 80.94
     },
     "aql": {
      "raw": 44.608,
      "sd": 1.256,
      "score": 79.08
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 392.833,
      "sd": 1.597,
      "score": 94.4
     },
     "awt": {
      "raw": 91.283,
      "sd": 2.13,
      "score": 86.95
     },
     "aql": {
      "raw": 158.045,
      "sd": 3.988,
      "score": 81.6
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1036.414,
      "sd": 4.114,
      "score": 80.71
     },
     "awt": {
      "raw": 571.995,
      "sd": 0.792,
      "score": 78.67
     },
     "aql": {
      "raw": 1471.081,
      "sd": 3.722,
      "score": 71.06
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1330.399,
      "sd": 8.7,
      "score": 75.8
     },
     "awt": {
      "raw": 879.122,
      "sd": 11.446,
      "score": 77.16
     },
     "aql": {
      "raw": 2797.007,
      "sd": 35.609,
      "score": 66.8
     }
    }
   },
   "cost": {
    "gpu_seconds": 963.7,
    "serving_seconds": 283.2,
    "wall_seconds": 380.2,
    "tokens_per_task": null,
    "decisions_per_task": 12811,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 222.5,
     "jinan-2": 221.8,
     "jinan-3": 222.2,
     "hangzhou-1": 283.3,
     "hangzhou-2": 284.0,
     "newyork-1": 2722.4,
     "newyork-2": 2790.0
    }
   },
   "rank": 24,
   "pareto": false
  },
  {
   "id": "kev-27b::jevlight",
   "model": "kev-27b",
   "mode": "jevlight",
   "name": "Kev 27B",
   "family": "kev",
   "family_label": "Kev",
   "color": "#ffc531",
   "kind": "native",
   "hosted": false,
   "params_b": 27.0,
   "score": 87.22,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 318.215,
      "sd": 0.981,
      "score": 99.84
     },
     "awt": {
      "raw": 57.127,
      "sd": 0.569,
      "score": 99.46
     },
     "aql": {
      "raw": 99.624,
      "sd": 1.0,
      "score": 99.38
     }
    },
    "jinan-2": {
     "att": {
      "raw": 304.344,
      "sd": 0.897,
      "score": 99.65
     },
     "awt": {
      "raw": 39.905,
      "sd": 0.253,
      "score": 98.99
     },
     "aql": {
      "raw": 48.23,
      "sd": 0.308,
      "score": 98.9
     }
    },
    "jinan-3": {
     "att": {
      "raw": 298.177,
      "sd": 0.907,
      "score": 99.9
     },
     "awt": {
      "raw": 43.139,
      "sd": 0.441,
      "score": 99.83
     },
     "aql": {
      "raw": 65.621,
      "sd": 0.673,
      "score": 99.81
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 345.353,
      "sd": 1.108,
      "score": 99.23
     },
     "awt": {
      "raw": 28.34,
      "sd": 0.555,
      "score": 97.03
     },
     "aql": {
      "raw": 23.429,
      "sd": 0.459,
      "score": 96.72
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 381.377,
      "sd": 3.264,
      "score": 97.21
     },
     "awt": {
      "raw": 69.993,
      "sd": 2.165,
      "score": 97.03
     },
     "aql": {
      "raw": 117.524,
      "sd": 3.561,
      "score": 95.53
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1128.765,
      "sd": 5.693,
      "score": 70.38
     },
     "awt": {
      "raw": 712.725,
      "sd": 10.919,
      "score": 64.21
     },
     "aql": {
      "raw": 1802.28,
      "sd": 26.074,
      "score": 54.01
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1455.832,
      "sd": 3.248,
      "score": 61.44
     },
     "awt": {
      "raw": 1070.555,
      "sd": 4.435,
      "score": 58.79
     },
     "aql": {
      "raw": 3322.913,
      "sd": 6.285,
      "score": 44.27
     }
    }
   },
   "cost": {
    "gpu_seconds": 2560.3,
    "serving_seconds": 741.6,
    "wall_seconds": 8330.5,
    "tokens_per_task": 11029952,
    "decisions_per_task": 12663,
    "tokens_per_decision": 871.0,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 577.1,
     "jinan-2": 594.6,
     "jinan-3": 576.6,
     "hangzhou-1": 765.8,
     "hangzhou-2": 742.3,
     "newyork-1": 7287.0,
     "newyork-2": 7378.8
    }
   },
   "rank": 25,
   "pareto": false
  },
  {
   "id": "startlux-2b::jevlight",
   "model": "startlux-2b",
   "mode": "jevlight",
   "name": "StartLux 2B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 2.0,
   "score": 87.0,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 324.44,
      "sd": 0.634,
      "score": 98.59
     },
     "awt": {
      "raw": 61.523,
      "sd": 0.357,
      "score": 97.12
     },
     "aql": {
      "raw": 107.347,
      "sd": 0.631,
      "score": 96.72
     }
    },
    "jinan-2": {
     "att": {
      "raw": 305.759,
      "sd": 1.349,
      "score": 99.37
     },
     "awt": {
      "raw": 40.518,
      "sd": 0.746,
      "score": 98.57
     },
     "aql": {
      "raw": 48.963,
      "sd": 0.911,
      "score": 98.45
     }
    },
    "jinan-3": {
     "att": {
      "raw": 300.243,
      "sd": 0.528,
      "score": 99.47
     },
     "awt": {
      "raw": 44.617,
      "sd": 0.889,
      "score": 98.84
     },
     "aql": {
      "raw": 67.888,
      "sd": 1.33,
      "score": 98.72
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 346.483,
      "sd": 0.882,
      "score": 99.01
     },
     "awt": {
      "raw": 27.463,
      "sd": 0.096,
      "score": 97.81
     },
     "aql": {
      "raw": 22.698,
      "sd": 0.082,
      "score": 97.59
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 388.004,
      "sd": 1.919,
      "score": 95.57
     },
     "awt": {
      "raw": 70.423,
      "sd": 0.483,
      "score": 96.8
     },
     "aql": {
      "raw": 113.185,
      "sd": 1.355,
      "score": 97.3
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1137.93,
      "sd": 6.859,
      "score": 69.4
     },
     "awt": {
      "raw": 707.839,
      "sd": 8.454,
      "score": 64.66
     },
     "aql": {
      "raw": 1764.768,
      "sd": 20.883,
      "score": 55.77
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1466.329,
      "sd": 2.475,
      "score": 60.29
     },
     "awt": {
      "raw": 1073.619,
      "sd": 0.481,
      "score": 58.52
     },
     "aql": {
      "raw": 3217.688,
      "sd": 7.231,
      "score": 48.47
     }
    }
   },
   "cost": {
    "gpu_seconds": 291.8,
    "serving_seconds": 81.7,
    "wall_seconds": 209.0,
    "tokens_per_task": 11302900,
    "decisions_per_task": 12872,
    "tokens_per_decision": 878.1,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 70.0,
     "jinan-2": 70.1,
     "jinan-3": 70.2,
     "hangzhou-1": 83.0,
     "hangzhou-2": 81.7,
     "newyork-1": 831.5,
     "newyork-2": 835.8
    }
   },
   "rank": 26,
   "pareto": true
  },
  {
   "id": "lev::jevlight",
   "model": "lev",
   "mode": "jevlight",
   "name": "Lev",
   "family": "lev",
   "family_label": "Lev",
   "color": "#90a4ae",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 86.79,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 320.585,
      "sd": 1.063,
      "score": 99.36
     },
     "awt": {
      "raw": 60.219,
      "sd": 0.525,
      "score": 97.8
     },
     "aql": {
      "raw": 105.032,
      "sd": 0.909,
      "score": 97.5
     }
    },
    "jinan-2": {
     "att": {
      "raw": 307.538,
      "sd": 1.266,
      "score": 99.02
     },
     "awt": {
      "raw": 43.394,
      "sd": 0.719,
      "score": 96.67
     },
     "aql": {
      "raw": 52.465,
      "sd": 0.876,
      "score": 96.4
     }
    },
    "jinan-3": {
     "att": {
      "raw": 301.155,
      "sd": 1.59,
      "score": 99.27
     },
     "awt": {
      "raw": 46.893,
      "sd": 1.172,
      "score": 97.39
     },
     "aql": {
      "raw": 71.35,
      "sd": 1.789,
      "score": 97.11
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 351.88,
      "sd": 1.12,
      "score": 97.98
     },
     "awt": {
      "raw": 35.726,
      "sd": 0.276,
      "score": 91.23
     },
     "aql": {
      "raw": 29.549,
      "sd": 0.233,
      "score": 90.36
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 385.869,
      "sd": 1.294,
      "score": 96.1
     },
     "awt": {
      "raw": 81.329,
      "sd": 1.095,
      "score": 91.33
     },
     "aql": {
      "raw": 139.807,
      "sd": 2.327,
      "score": 87.37
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1082.632,
      "sd": 2.64,
      "score": 75.43
     },
     "awt": {
      "raw": 664.542,
      "sd": 6.453,
      "score": 68.81
     },
     "aql": {
      "raw": 1679.729,
      "sd": 13.931,
      "score": 59.92
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1402.23,
      "sd": 2.421,
      "score": 67.42
     },
     "awt": {
      "raw": 1017.342,
      "sd": 6.176,
      "score": 63.55
     },
     "aql": {
      "raw": 3119.743,
      "sd": 5.877,
      "score": 52.52
     }
    }
   },
   "cost": {
    "gpu_seconds": 1559.6,
    "serving_seconds": 443.7,
    "wall_seconds": null,
    "tokens_per_task": 15023094,
    "decisions_per_task": 12715,
    "tokens_per_decision": 1181.5,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 344.7,
     "jinan-2": 350.8,
     "jinan-3": 342.8,
     "hangzhou-1": 475.3,
     "hangzhou-2": 445.2,
     "newyork-1": 4609.0,
     "newyork-2": 4349.4
    }
   },
   "rank": 27,
   "pareto": false
  },
  {
   "id": "startlux-9b::cojevlight",
   "model": "startlux-9b",
   "mode": "cojevlight",
   "name": "StartLux 9B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 9.0,
   "score": 84.21,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 377.813,
      "sd": 40.649,
      "score": 88.77
     },
     "awt": {
      "raw": 114.67,
      "sd": 40.33,
      "score": 77.53
     },
     "aql": {
      "raw": 186.658,
      "sd": 59.296,
      "score": 76.99
     }
    },
    "jinan-2": {
     "att": {
      "raw": 310.22,
      "sd": 2.026,
      "score": 98.5
     },
     "awt": {
      "raw": 45.131,
      "sd": 1.726,
      "score": 95.59
     },
     "aql": {
      "raw": 54.574,
      "sd": 2.088,
      "score": 95.23
     }
    },
    "jinan-3": {
     "att": {
      "raw": 339.542,
      "sd": 29.778,
      "score": 91.7
     },
     "awt": {
      "raw": 81.424,
      "sd": 28.488,
      "score": 81.23
     },
     "aql": {
      "raw": 120.374,
      "sd": 40.135,
      "score": 80.25
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 347.362,
      "sd": 1.276,
      "score": 98.84
     },
     "awt": {
      "raw": 29.555,
      "sd": 0.912,
      "score": 95.98
     },
     "aql": {
      "raw": 24.426,
      "sd": 0.75,
      "score": 95.58
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 383.354,
      "sd": 2.035,
      "score": 96.72
     },
     "awt": {
      "raw": 75.054,
      "sd": 1.993,
      "score": 94.38
     },
     "aql": {
      "raw": 120.537,
      "sd": 3.105,
      "score": 94.34
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1082.089,
      "sd": 9.161,
      "score": 75.49
     },
     "awt": {
      "raw": 691.48,
      "sd": 13.939,
      "score": 66.2
     },
     "aql": {
      "raw": 1767.833,
      "sd": 31.423,
      "score": 55.63
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1343.812,
      "sd": 7.411,
      "score": 74.2
     },
     "awt": {
      "raw": 941.226,
      "sd": 10.277,
      "score": 70.8
     },
     "aql": {
      "raw": 2849.358,
      "sd": 29.468,
      "score": 64.38
     }
    }
   },
   "cost": {
    "gpu_seconds": 2329.6,
    "serving_seconds": 655.2,
    "wall_seconds": 796.9,
    "tokens_per_task": 26853556,
    "decisions_per_task": 12732,
    "tokens_per_decision": 2109.1,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 398.2,
     "jinan-2": 375.6,
     "jinan-3": 391.6,
     "hangzhou-1": 2595.9,
     "hangzhou-2": 660.9,
     "newyork-1": 5817.1,
     "newyork-2": 6068.2
    }
   },
   "rank": 28,
   "pareto": false
  },
  {
   "id": "valen-4b::jevlight",
   "model": "valen-4b",
   "mode": "jevlight",
   "name": "Valen 4B",
   "family": "valen",
   "family_label": "Valen",
   "color": "#6cb6ff",
   "kind": "native",
   "hosted": false,
   "params_b": 4.0,
   "score": 84.12,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 319.841,
      "sd": 0.763,
      "score": 99.51
     },
     "awt": {
      "raw": 58.711,
      "sd": 0.533,
      "score": 98.59
     },
     "aql": {
      "raw": 102.404,
      "sd": 0.937,
      "score": 98.4
     }
    },
    "jinan-2": {
     "att": {
      "raw": 305.081,
      "sd": 1.347,
      "score": 99.51
     },
     "awt": {
      "raw": 40.677,
      "sd": 1.019,
      "score": 98.46
     },
     "aql": {
      "raw": 49.165,
      "sd": 1.251,
      "score": 98.33
     }
    },
    "jinan-3": {
     "att": {
      "raw": 299.266,
      "sd": 0.628,
      "score": 99.67
     },
     "awt": {
      "raw": 44.324,
      "sd": 0.223,
      "score": 99.04
     },
     "aql": {
      "raw": 67.444,
      "sd": 0.328,
      "score": 98.93
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 346.043,
      "sd": 1.102,
      "score": 99.1
     },
     "awt": {
      "raw": 28.982,
      "sd": 0.296,
      "score": 96.47
     },
     "aql": {
      "raw": 23.959,
      "sd": 0.235,
      "score": 96.11
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 378.411,
      "sd": 1.756,
      "score": 97.96
     },
     "awt": {
      "raw": 75.097,
      "sd": 0.801,
      "score": 94.36
     },
     "aql": {
      "raw": 128.569,
      "sd": 1.535,
      "score": 91.31
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1184.912,
      "sd": 3.71,
      "score": 64.51
     },
     "awt": {
      "raw": 808.371,
      "sd": 4.34,
      "score": 55.93
     },
     "aql": {
      "raw": 2053.922,
      "sd": 4.284,
      "score": 43.03
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1524.793,
      "sd": 4.818,
      "score": 54.06
     },
     "awt": {
      "raw": 1195.583,
      "sd": 5.924,
      "score": 48.49
     },
     "aql": {
      "raw": 3572.846,
      "sd": 23.266,
      "score": 34.78
     }
    }
   },
   "cost": {
    "gpu_seconds": 522.3,
    "serving_seconds": 153.0,
    "wall_seconds": null,
    "tokens_per_task": 10810729,
    "decisions_per_task": 12697,
    "tokens_per_decision": 851.4,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 122.0,
     "jinan-2": 124.6,
     "jinan-3": 122.5,
     "hangzhou-1": 156.6,
     "hangzhou-2": 153.0,
     "newyork-1": 1475.6,
     "newyork-2": 1501.6
    }
   },
   "rank": 29,
   "pareto": false
  },
  {
   "id": "clef-27b::jevlight",
   "model": "clef-27b",
   "mode": "jevlight",
   "name": "Clef 27B",
   "family": "clef",
   "family_label": "Clef",
   "color": "#ff8a65",
   "kind": "native",
   "hosted": false,
   "params_b": 27.0,
   "score": 83.06,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 320.106,
      "sd": 2.627,
      "score": 99.46
     },
     "awt": {
      "raw": 61.227,
      "sd": 1.855,
      "score": 97.27
     },
     "aql": {
      "raw": 106.809,
      "sd": 3.25,
      "score": 96.9
     }
    },
    "jinan-2": {
     "att": {
      "raw": 310.967,
      "sd": 0.741,
      "score": 98.35
     },
     "awt": {
      "raw": 47.639,
      "sd": 0.272,
      "score": 94.09
     },
     "aql": {
      "raw": 57.621,
      "sd": 0.322,
      "score": 93.62
     }
    },
    "jinan-3": {
     "att": {
      "raw": 304.112,
      "sd": 0.846,
      "score": 98.66
     },
     "awt": {
      "raw": 50.651,
      "sd": 0.452,
      "score": 95.13
     },
     "aql": {
      "raw": 77.096,
      "sd": 0.701,
      "score": 94.62
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 365.596,
      "sd": 1.489,
      "score": 95.45
     },
     "awt": {
      "raw": 50.844,
      "sd": 0.972,
      "score": 82.4
     },
     "aql": {
      "raw": 42.076,
      "sd": 0.811,
      "score": 80.68
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 393.759,
      "sd": 0.997,
      "score": 94.17
     },
     "awt": {
      "raw": 98.678,
      "sd": 1.138,
      "score": 83.99
     },
     "aql": {
      "raw": 173.975,
      "sd": 2.196,
      "score": 77.08
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1084.643,
      "sd": 3.728,
      "score": 75.21
     },
     "awt": {
      "raw": 673.8,
      "sd": 2.875,
      "score": 67.9
     },
     "aql": {
      "raw": 1777.137,
      "sd": 8.099,
      "score": 55.19
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1434.696,
      "sd": 17.905,
      "score": 63.77
     },
     "awt": {
      "raw": 1061.271,
      "sd": 21.487,
      "score": 59.6
     },
     "aql": {
      "raw": 3412.341,
      "sd": 51.294,
      "score": 40.79
     }
    }
   },
   "cost": {
    "gpu_seconds": 2514.2,
    "serving_seconds": 738.7,
    "wall_seconds": 856.4,
    "tokens_per_task": 10442899,
    "decisions_per_task": 12565,
    "tokens_per_decision": 831.1,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 579.6,
     "jinan-2": 593.1,
     "jinan-3": 577.6,
     "hangzhou-1": 758.9,
     "hangzhou-2": 751.9,
     "newyork-1": 7228.1,
     "newyork-2": 7110.5
    }
   },
   "rank": 30,
   "pareto": false
  },
  {
   "id": "startlux-4b::cojevlight",
   "model": "startlux-4b",
   "mode": "cojevlight",
   "name": "StartLux 4B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 4.0,
   "score": 82.37,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 409.242,
      "sd": 11.749,
      "score": 83.61
     },
     "awt": {
      "raw": 150.53,
      "sd": 13.531,
      "score": 68.96
     },
     "aql": {
      "raw": 240.574,
      "sd": 20.219,
      "score": 67.94
     }
    },
    "jinan-2": {
     "att": {
      "raw": 313.327,
      "sd": 1.857,
      "score": 97.9
     },
     "awt": {
      "raw": 47.783,
      "sd": 1.455,
      "score": 94.01
     },
     "aql": {
      "raw": 57.786,
      "sd": 1.754,
      "score": 93.54
     }
    },
    "jinan-3": {
     "att": {
      "raw": 355.521,
      "sd": 5.858,
      "score": 88.8
     },
     "awt": {
      "raw": 96.563,
      "sd": 5.511,
      "score": 76.24
     },
     "aql": {
      "raw": 141.894,
      "sd": 7.573,
      "score": 74.95
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 349.936,
      "sd": 1.166,
      "score": 98.35
     },
     "awt": {
      "raw": 31.226,
      "sd": 0.629,
      "score": 94.6
     },
     "aql": {
      "raw": 25.813,
      "sd": 0.517,
      "score": 94.06
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 392.971,
      "sd": 3.273,
      "score": 94.36
     },
     "awt": {
      "raw": 88.866,
      "sd": 2.965,
      "score": 87.97
     },
     "aql": {
      "raw": 135.073,
      "sd": 3.953,
      "score": 88.99
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1073.454,
      "sd": 15.161,
      "score": 76.46
     },
     "awt": {
      "raw": 668.261,
      "sd": 30.23,
      "score": 68.45
     },
     "aql": {
      "raw": 1639.309,
      "sd": 78.153,
      "score": 61.97
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1309.262,
      "sd": 28.37,
      "score": 78.36
     },
     "awt": {
      "raw": 933.239,
      "sd": 35.047,
      "score": 71.59
     },
     "aql": {
      "raw": 2755.714,
      "sd": 95.451,
      "score": 68.75
     }
    }
   },
   "cost": {
    "gpu_seconds": 1226.9,
    "serving_seconds": 405.6,
    "wall_seconds": 554.7,
    "tokens_per_task": 26993613,
    "decisions_per_task": 12971,
    "tokens_per_decision": 2081.1,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 402.8,
     "jinan-2": 353.8,
     "jinan-3": 388.4,
     "hangzhou-1": 375.0,
     "hangzhou-2": 408.7,
     "newyork-1": 3282.6,
     "newyork-2": 3377.3
    }
   },
   "rank": 31,
   "pareto": false
  },
  {
   "id": "kev-9b::cojevlight",
   "model": "kev-9b",
   "mode": "cojevlight",
   "name": "Kev 9B",
   "family": "kev",
   "family_label": "Kev",
   "color": "#ffc531",
   "kind": "native",
   "hosted": false,
   "params_b": 9.0,
   "score": 82.19,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 323.16,
      "sd": 1.664,
      "score": 98.85
     },
     "awt": {
      "raw": 62.198,
      "sd": 1.174,
      "score": 96.78
     },
     "aql": {
      "raw": 108.493,
      "sd": 2.047,
      "score": 96.34
     }
    },
    "jinan-2": {
     "att": {
      "raw": 308.935,
      "sd": 1.071,
      "score": 98.75
     },
     "awt": {
      "raw": 44.515,
      "sd": 0.645,
      "score": 95.97
     },
     "aql": {
      "raw": 53.816,
      "sd": 0.792,
      "score": 95.65
     }
    },
    "jinan-3": {
     "att": {
      "raw": 303.317,
      "sd": 1.557,
      "score": 98.82
     },
     "awt": {
      "raw": 48.576,
      "sd": 0.86,
      "score": 96.36
     },
     "aql": {
      "raw": 73.923,
      "sd": 1.306,
      "score": 95.97
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 350.186,
      "sd": 1.347,
      "score": 98.31
     },
     "awt": {
      "raw": 34.057,
      "sd": 1.297,
      "score": 92.43
     },
     "aql": {
      "raw": 28.166,
      "sd": 1.072,
      "score": 91.67
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 374.373,
      "sd": 2.651,
      "score": 98.98
     },
     "awt": {
      "raw": 73.01,
      "sd": 2.337,
      "score": 95.43
     },
     "aql": {
      "raw": 122.094,
      "sd": 4.432,
      "score": 93.74
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1229.35,
      "sd": 13.91,
      "score": 60.06
     },
     "awt": {
      "raw": 876.076,
      "sd": 17.769,
      "score": 50.64
     },
     "aql": {
      "raw": 2213.281,
      "sd": 25.087,
      "score": 36.76
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1515.459,
      "sd": 2.007,
      "score": 55.03
     },
     "awt": {
      "raw": 1188.92,
      "sd": 2.716,
      "score": 49.01
     },
     "aql": {
      "raw": 3690.649,
      "sd": 16.103,
      "score": 30.54
     }
    }
   },
   "cost": {
    "gpu_seconds": 2280.1,
    "serving_seconds": 803.9,
    "wall_seconds": null,
    "tokens_per_task": 26180729,
    "decisions_per_task": 12241,
    "tokens_per_decision": 2138.8,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 808.7,
     "jinan-2": 698.1,
     "jinan-3": 775.9,
     "hangzhou-1": 694.0,
     "hangzhou-2": 814.2,
     "newyork-1": 6113.9,
     "newyork-2": 6056.2
    }
   },
   "rank": 32,
   "pareto": false
  },
  {
   "id": "kev-4b::jevlight",
   "model": "kev-4b",
   "mode": "jevlight",
   "name": "Kev 4B",
   "family": "kev",
   "family_label": "Kev",
   "color": "#ffc531",
   "kind": "native",
   "hosted": false,
   "params_b": 4.0,
   "score": 80.51,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 338.338,
      "sd": 1.928,
      "score": 95.89
     },
     "awt": {
      "raw": 76.735,
      "sd": 1.513,
      "score": 90.17
     },
     "aql": {
      "raw": 133.927,
      "sd": 2.628,
      "score": 88.83
     }
    },
    "jinan-2": {
     "att": {
      "raw": 315.11,
      "sd": 1.433,
      "score": 97.56
     },
     "awt": {
      "raw": 50.868,
      "sd": 0.975,
      "score": 92.28
     },
     "aql": {
      "raw": 61.517,
      "sd": 1.167,
      "score": 91.68
     }
    },
    "jinan-3": {
     "att": {
      "raw": 312.424,
      "sd": 1.89,
      "score": 96.96
     },
     "awt": {
      "raw": 57.373,
      "sd": 1.717,
      "score": 91.48
     },
     "aql": {
      "raw": 87.345,
      "sd": 2.631,
      "score": 90.59
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 358.993,
      "sd": 2.105,
      "score": 96.66
     },
     "awt": {
      "raw": 42.047,
      "sd": 1.202,
      "score": 87.15
     },
     "aql": {
      "raw": 34.782,
      "sd": 0.991,
      "score": 85.89
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 413.094,
      "sd": 3.144,
      "score": 89.62
     },
     "awt": {
      "raw": 100.484,
      "sd": 2.627,
      "score": 83.3
     },
     "aql": {
      "raw": 161.055,
      "sd": 3.482,
      "score": 80.71
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1179.325,
      "sd": 9.313,
      "score": 65.08
     },
     "awt": {
      "raw": 800.834,
      "sd": 19.211,
      "score": 56.55
     },
     "aql": {
      "raw": 2016.702,
      "sd": 40.69,
      "score": 44.57
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1440.48,
      "sd": 4.42,
      "score": 63.13
     },
     "awt": {
      "raw": 1081.272,
      "sd": 6.35,
      "score": 57.86
     },
     "aql": {
      "raw": 3312.796,
      "sd": 13.357,
      "score": 44.66
     }
    }
   },
   "cost": {
    "gpu_seconds": 590.4,
    "serving_seconds": 176.6,
    "wall_seconds": 277.9,
    "tokens_per_task": null,
    "decisions_per_task": 12769,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 137.1,
     "jinan-2": 136.9,
     "jinan-3": 136.4,
     "hangzhou-1": 177.4,
     "hangzhou-2": 176.8,
     "newyork-1": 1660.8,
     "newyork-2": 1707.2
    }
   },
   "rank": 33,
   "pareto": false
  },
  {
   "id": "decider-4b::cojevlight",
   "model": "decider-4b",
   "mode": "cojevlight",
   "name": "Decider 4B",
   "family": "decider",
   "family_label": "Decider",
   "color": "#aed581",
   "kind": "native",
   "hosted": false,
   "params_b": 4.0,
   "score": 79.71,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 373.643,
      "sd": 7.897,
      "score": 89.48
     },
     "awt": {
      "raw": 111.349,
      "sd": 8.493,
      "score": 78.45
     },
     "aql": {
      "raw": 191.994,
      "sd": 13.696,
      "score": 75.98
     }
    },
    "jinan-2": {
     "att": {
      "raw": 341.584,
      "sd": 3.962,
      "score": 92.69
     },
     "awt": {
      "raw": 76.681,
      "sd": 4.012,
      "score": 80.94
     },
     "aql": {
      "raw": 92.838,
      "sd": 4.869,
      "score": 79.46
     }
    },
    "jinan-3": {
     "att": {
      "raw": 348.721,
      "sd": 7.591,
      "score": 90.02
     },
     "awt": {
      "raw": 91.196,
      "sd": 6.377,
      "score": 77.91
     },
     "aql": {
      "raw": 138.999,
      "sd": 9.733,
      "score": 75.61
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 367.093,
      "sd": 2.559,
      "score": 95.17
     },
     "awt": {
      "raw": 51.826,
      "sd": 1.506,
      "score": 81.92
     },
     "aql": {
      "raw": 42.882,
      "sd": 1.242,
      "score": 80.16
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 397.909,
      "sd": 2.625,
      "score": 93.18
     },
     "awt": {
      "raw": 97.46,
      "sd": 3.776,
      "score": 84.46
     },
     "aql": {
      "raw": 158.785,
      "sd": 5.818,
      "score": 81.38
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1057.645,
      "sd": 6.472,
      "score": 78.26
     },
     "awt": {
      "raw": 635.157,
      "sd": 14.132,
      "score": 71.79
     },
     "aql": {
      "raw": 1621.954,
      "sd": 27.924,
      "score": 62.86
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1348.025,
      "sd": 6.305,
      "score": 73.7
     },
     "awt": {
      "raw": 940.523,
      "sd": 8.434,
      "score": 70.87
     },
     "aql": {
      "raw": 2956.785,
      "sd": 21.842,
      "score": 59.54
     }
    }
   },
   "cost": {
    "gpu_seconds": 1279.4,
    "serving_seconds": 434.4,
    "wall_seconds": null,
    "tokens_per_task": 26216476,
    "decisions_per_task": 12341,
    "tokens_per_decision": 2124.3,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 441.6,
     "jinan-2": 392.9,
     "jinan-3": 428.2,
     "hangzhou-1": 382.4,
     "hangzhou-2": 439.2,
     "newyork-1": 3473.2,
     "newyork-2": 3398.6
    }
   },
   "rank": 34,
   "pareto": false
  },
  {
   "id": "startlux-0.8b::jevlight",
   "model": "startlux-0.8b",
   "mode": "jevlight",
   "name": "StartLux 0.8B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 0.8,
   "score": 76.77,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 377.753,
      "sd": 1.772,
      "score": 88.78
     },
     "awt": {
      "raw": 105.742,
      "sd": 0.8,
      "score": 80.08
     },
     "aql": {
      "raw": 184.253,
      "sd": 1.374,
      "score": 77.45
     }
    },
    "jinan-2": {
     "att": {
      "raw": 339.898,
      "sd": 0.536,
      "score": 92.99
     },
     "awt": {
      "raw": 74.425,
      "sd": 0.576,
      "score": 81.76
     },
     "aql": {
      "raw": 90.092,
      "sd": 0.681,
      "score": 80.35
     }
    },
    "jinan-3": {
     "att": {
      "raw": 346.996,
      "sd": 3.843,
      "score": 90.33
     },
     "awt": {
      "raw": 85.702,
      "sd": 2.636,
      "score": 79.73
     },
     "aql": {
      "raw": 130.584,
      "sd": 4.015,
      "score": 77.63
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 387.399,
      "sd": 2.823,
      "score": 91.6
     },
     "awt": {
      "raw": 69.669,
      "sd": 2.129,
      "score": 74.51
     },
     "aql": {
      "raw": 57.677,
      "sd": 1.767,
      "score": 72.03
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 423.251,
      "sd": 2.638,
      "score": 87.3
     },
     "awt": {
      "raw": 118.799,
      "sd": 1.581,
      "score": 76.94
     },
     "aql": {
      "raw": 195.564,
      "sd": 2.737,
      "score": 71.58
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1142.034,
      "sd": 11.458,
      "score": 68.97
     },
     "awt": {
      "raw": 707.363,
      "sd": 15.401,
      "score": 64.71
     },
     "aql": {
      "raw": 1699.882,
      "sd": 44.118,
      "score": 58.92
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1398.355,
      "sd": 7.677,
      "score": 67.86
     },
     "awt": {
      "raw": 969.491,
      "sd": 7.556,
      "score": 68.04
     },
     "aql": {
      "raw": 2930.86,
      "sd": 31.525,
      "score": 60.69
     }
    }
   },
   "cost": {
    "gpu_seconds": 213.1,
    "serving_seconds": 59.4,
    "wall_seconds": 206.7,
    "tokens_per_task": 11297785,
    "decisions_per_task": 12851,
    "tokens_per_decision": 879.1,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 54.6,
     "jinan-2": 52.9,
     "jinan-3": 52.7,
     "hangzhou-1": 59.4,
     "hangzhou-2": 59.9,
     "newyork-1": 597.5,
     "newyork-2": 614.7
    }
   },
   "rank": 35,
   "pareto": true
  },
  {
   "id": "decider-4b::jevlight",
   "model": "decider-4b",
   "mode": "jevlight",
   "name": "Decider 4B",
   "family": "decider",
   "family_label": "Decider",
   "color": "#aed581",
   "kind": "native",
   "hosted": false,
   "params_b": 4.0,
   "score": 75.97,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 345.311,
      "sd": 1.583,
      "score": 94.57
     },
     "awt": {
      "raw": 87.71,
      "sd": 0.789,
      "score": 85.96
     },
     "aql": {
      "raw": 153.13,
      "sd": 1.371,
      "score": 84.05
     }
    },
    "jinan-2": {
     "att": {
      "raw": 330.332,
      "sd": 2.42,
      "score": 94.71
     },
     "awt": {
      "raw": 67.542,
      "sd": 1.791,
      "score": 84.45
     },
     "aql": {
      "raw": 81.749,
      "sd": 2.163,
      "score": 83.24
     }
    },
    "jinan-3": {
     "att": {
      "raw": 327.088,
      "sd": 0.825,
      "score": 94.06
     },
     "awt": {
      "raw": 74.372,
      "sd": 0.66,
      "score": 83.88
     },
     "aql": {
      "raw": 113.302,
      "sd": 1.015,
      "score": 82.21
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 389.633,
      "sd": 1.794,
      "score": 91.22
     },
     "awt": {
      "raw": 76.149,
      "sd": 1.504,
      "score": 72.28
     },
     "aql": {
      "raw": 63.049,
      "sd": 1.242,
      "score": 69.59
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 424.499,
      "sd": 3.514,
      "score": 87.02
     },
     "awt": {
      "raw": 135.751,
      "sd": 2.707,
      "score": 71.88
     },
     "aql": {
      "raw": 241.326,
      "sd": 4.696,
      "score": 61.69
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1089.526,
      "sd": 6.607,
      "score": 74.66
     },
     "awt": {
      "raw": 683.384,
      "sd": 6.497,
      "score": 66.97
     },
     "aql": {
      "raw": 1767.614,
      "sd": 21.317,
      "score": 55.64
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1459.93,
      "sd": 7.96,
      "score": 60.99
     },
     "awt": {
      "raw": 1105.052,
      "sd": 10.367,
      "score": 55.83
     },
     "aql": {
      "raw": 3421.051,
      "sd": 21.989,
      "score": 40.46
     }
    }
   },
   "cost": {
    "gpu_seconds": 498.2,
    "serving_seconds": 148.8,
    "wall_seconds": null,
    "tokens_per_task": 10493814,
    "decisions_per_task": 12485,
    "tokens_per_decision": 840.5,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 119.0,
     "jinan-2": 120.4,
     "jinan-3": 118.5,
     "hangzhou-1": 152.6,
     "hangzhou-2": 148.8,
     "newyork-1": 1423.6,
     "newyork-2": 1404.6
    }
   },
   "rank": 36,
   "pareto": false
  },
  {
   "id": "valen-4b::cojevlight",
   "model": "valen-4b",
   "mode": "cojevlight",
   "name": "Valen 4B",
   "family": "valen",
   "family_label": "Valen",
   "color": "#6cb6ff",
   "kind": "native",
   "hosted": false,
   "params_b": 4.0,
   "score": 75.74,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 326.217,
      "sd": 1.078,
      "score": 98.24
     },
     "awt": {
      "raw": 64.699,
      "sd": 0.781,
      "score": 95.54
     },
     "aql": {
      "raw": 112.877,
      "sd": 1.374,
      "score": 94.93
     }
    },
    "jinan-2": {
     "att": {
      "raw": 315.803,
      "sd": 3.417,
      "score": 97.42
     },
     "awt": {
      "raw": 51.803,
      "sd": 2.469,
      "score": 91.78
     },
     "aql": {
      "raw": 62.662,
      "sd": 2.995,
      "score": 91.13
     }
    },
    "jinan-3": {
     "att": {
      "raw": 307.759,
      "sd": 0.298,
      "score": 97.91
     },
     "awt": {
      "raw": 53.396,
      "sd": 0.237,
      "score": 93.59
     },
     "aql": {
      "raw": 81.304,
      "sd": 0.36,
      "score": 92.9
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 389.803,
      "sd": 3.107,
      "score": 91.19
     },
     "awt": {
      "raw": 74.448,
      "sd": 2.228,
      "score": 72.85
     },
     "aql": {
      "raw": 61.636,
      "sd": 1.852,
      "score": 70.22
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 428.941,
      "sd": 6.877,
      "score": 86.03
     },
     "awt": {
      "raw": 139.057,
      "sd": 7.479,
      "score": 70.96
     },
     "aql": {
      "raw": 241.418,
      "sd": 11.774,
      "score": 61.68
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1186.073,
      "sd": 124.339,
      "score": 64.39
     },
     "awt": {
      "raw": 838.79,
      "sd": 161.39,
      "score": 53.5
     },
     "aql": {
      "raw": 2089.181,
      "sd": 334.076,
      "score": 41.6
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1556.513,
      "sd": 10.638,
      "score": 50.77
     },
     "awt": {
      "raw": 1252.306,
      "sd": 12.045,
      "score": 44.17
     },
     "aql": {
      "raw": 3710.972,
      "sd": 23.468,
      "score": 29.82
     }
    }
   },
   "cost": {
    "gpu_seconds": 1202.2,
    "serving_seconds": 419.2,
    "wall_seconds": null,
    "tokens_per_task": 25732329,
    "decisions_per_task": 12207,
    "tokens_per_decision": 2107.9,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 419.2,
     "jinan-2": 376.4,
     "jinan-3": 409.1,
     "hangzhou-1": 385.3,
     "hangzhou-2": 437.5,
     "newyork-1": 3102.3,
     "newyork-2": 3285.4
    }
   },
   "rank": 37,
   "pareto": false
  },
  {
   "id": "bespoke-nimble-9b::jevlight",
   "model": "bespoke-nimble-9b",
   "mode": "jevlight",
   "name": "Bespoke-Nimble 9B",
   "family": "bespoke",
   "family_label": "Bespoke",
   "color": "#ba68c8",
   "kind": "native",
   "hosted": false,
   "params_b": 9.0,
   "score": 73.64,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 337.934,
      "sd": 1.499,
      "score": 95.96
     },
     "awt": {
      "raw": 79.536,
      "sd": 1.411,
      "score": 89.04
     },
     "aql": {
      "raw": 138.831,
      "sd": 2.48,
      "score": 87.55
     }
    },
    "jinan-2": {
     "att": {
      "raw": 326.655,
      "sd": 1.711,
      "score": 95.39
     },
     "awt": {
      "raw": 63.846,
      "sd": 0.985,
      "score": 86.0
     },
     "aql": {
      "raw": 77.268,
      "sd": 1.197,
      "score": 84.91
     }
    },
    "jinan-3": {
     "att": {
      "raw": 319.053,
      "sd": 1.381,
      "score": 95.63
     },
     "awt": {
      "raw": 65.63,
      "sd": 1.404,
      "score": 87.55
     },
     "aql": {
      "raw": 99.958,
      "sd": 2.129,
      "score": 86.24
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 381.439,
      "sd": 0.767,
      "score": 92.63
     },
     "awt": {
      "raw": 67.386,
      "sd": 1.167,
      "score": 75.34
     },
     "aql": {
      "raw": 55.784,
      "sd": 0.962,
      "score": 72.95
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 408.662,
      "sd": 3.638,
      "score": 90.64
     },
     "awt": {
      "raw": 113.996,
      "sd": 4.649,
      "score": 78.51
     },
     "aql": {
      "raw": 198.383,
      "sd": 8.281,
      "score": 70.91
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1283.324,
      "sd": 36.511,
      "score": 54.86
     },
     "awt": {
      "raw": 953.182,
      "sd": 49.572,
      "score": 45.09
     },
     "aql": {
      "raw": 2257.838,
      "sd": 85.307,
      "score": 35.09
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1577.903,
      "sd": 9.759,
      "score": 48.6
     },
     "awt": {
      "raw": 1268.164,
      "sd": 9.699,
      "score": 42.99
     },
     "aql": {
      "raw": 3689.308,
      "sd": 14.535,
      "score": 30.58
     }
    }
   },
   "cost": {
    "gpu_seconds": 1372.9,
    "serving_seconds": 412.9,
    "wall_seconds": 513.8,
    "tokens_per_task": null,
    "decisions_per_task": 12340,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 322.1,
     "jinan-2": 323.7,
     "jinan-3": 324.0,
     "hangzhou-1": 415.6,
     "hangzhou-2": 412.9,
     "newyork-1": 3850.0,
     "newyork-2": 3961.9
    }
   },
   "rank": 38,
   "pareto": false
  },
  {
   "id": "startlux-2b::cojevlight",
   "model": "startlux-2b",
   "mode": "cojevlight",
   "name": "StartLux 2B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 2.0,
   "score": 51.09,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 653.24,
      "sd": 16.036,
      "score": 53.44
     },
     "awt": {
      "raw": 410.825,
      "sd": 17.12,
      "score": 37.36
     },
     "aql": {
      "raw": 614.621,
      "sd": 22.539,
      "score": 34.48
     }
    },
    "jinan-2": {
     "att": {
      "raw": 616.322,
      "sd": 24.242,
      "score": 57.09
     },
     "awt": {
      "raw": 351.138,
      "sd": 24.412,
      "score": 38.9
     },
     "aql": {
      "raw": 397.86,
      "sd": 25.995,
      "score": 36.26
     }
    },
    "jinan-3": {
     "att": {
      "raw": 627.464,
      "sd": 6.963,
      "score": 52.94
     },
     "awt": {
      "raw": 384.921,
      "sd": 8.012,
      "score": 35.76
     },
     "aql": {
      "raw": 508.363,
      "sd": 10.179,
      "score": 33.81
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 578.203,
      "sd": 16.688,
      "score": 65.01
     },
     "awt": {
      "raw": 258.336,
      "sd": 20.143,
      "score": 41.7
     },
     "aql": {
      "raw": 209.878,
      "sd": 13.105,
      "score": 36.64
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 533.605,
      "sd": 8.477,
      "score": 65.27
     },
     "awt": {
      "raw": 269.762,
      "sd": 7.901,
      "score": 45.8
     },
     "aql": {
      "raw": 380.845,
      "sd": 7.423,
      "score": 40.24
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1163.861,
      "sd": 26.064,
      "score": 66.68
     },
     "awt": {
      "raw": 768.602,
      "sd": 26.057,
      "score": 59.25
     },
     "aql": {
      "raw": 1754.856,
      "sd": 56.841,
      "score": 56.25
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1336.462,
      "sd": 27.943,
      "score": 75.08
     },
     "awt": {
      "raw": 944.698,
      "sd": 42.463,
      "score": 70.45
     },
     "aql": {
      "raw": 2718.724,
      "sd": 97.483,
      "score": 70.52
     }
    }
   },
   "cost": {
    "gpu_seconds": 549.8,
    "serving_seconds": 183.4,
    "wall_seconds": 350.6,
    "tokens_per_task": 26426842,
    "decisions_per_task": 12498,
    "tokens_per_decision": 2114.5,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 186.4,
     "jinan-2": 175.6,
     "jinan-3": 179.1,
     "hangzhou-1": 164.7,
     "hangzhou-2": 173.2,
     "newyork-1": 1451.6,
     "newyork-2": 1518.0
    }
   },
   "rank": 39,
   "pareto": false
  },
  {
   "id": "kev-4b::cojevlight",
   "model": "kev-4b",
   "mode": "cojevlight",
   "name": "Kev 4B",
   "family": "kev",
   "family_label": "Kev",
   "color": "#ffc531",
   "kind": "native",
   "hosted": false,
   "params_b": 4.0,
   "score": 48.82,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 610.841,
      "sd": 21.124,
      "score": 57.77
     },
     "awt": {
      "raw": 366.049,
      "sd": 21.244,
      "score": 40.99
     },
     "aql": {
      "raw": 597.799,
      "sd": 34.715,
      "score": 35.47
     }
    },
    "jinan-2": {
     "att": {
      "raw": 545.206,
      "sd": 6.935,
      "score": 64.49
     },
     "awt": {
      "raw": 283.289,
      "sd": 4.995,
      "score": 44.83
     },
     "aql": {
      "raw": 342.505,
      "sd": 5.859,
      "score": 40.71
     }
    },
    "jinan-3": {
     "att": {
      "raw": 588.191,
      "sd": 16.558,
      "score": 57.02
     },
     "awt": {
      "raw": 342.994,
      "sd": 17.735,
      "score": 39.13
     },
     "aql": {
      "raw": 503.488,
      "sd": 24.401,
      "score": 34.12
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 449.345,
      "sd": 12.722,
      "score": 81.75
     },
     "awt": {
      "raw": 135.819,
      "sd": 11.438,
      "score": 57.8
     },
     "aql": {
      "raw": 112.501,
      "sd": 9.47,
      "score": 53.73
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 508.052,
      "sd": 9.599,
      "score": 69.94
     },
     "awt": {
      "raw": 244.116,
      "sd": 9.094,
      "score": 49.6
     },
     "aql": {
      "raw": 383.901,
      "sd": 10.631,
      "score": 39.86
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1330.353,
      "sd": 6.837,
      "score": 50.5
     },
     "awt": {
      "raw": 1027.539,
      "sd": 9.684,
      "score": 40.15
     },
     "aql": {
      "raw": 2390.492,
      "sd": 13.68,
      "score": 30.29
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1524.859,
      "sd": 18.68,
      "score": 54.05
     },
     "awt": {
      "raw": 1225.956,
      "sd": 24.734,
      "score": 46.15
     },
     "aql": {
      "raw": 3516.201,
      "sd": 63.576,
      "score": 36.87
     }
    }
   },
   "cost": {
    "gpu_seconds": 1294.5,
    "serving_seconds": 469.0,
    "wall_seconds": 635.1,
    "tokens_per_task": null,
    "decisions_per_task": 11708,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 483.4,
     "jinan-2": 448.9,
     "jinan-3": 469.0,
     "hangzhou-1": 442.3,
     "hangzhou-2": 465.2,
     "newyork-1": 3331.8,
     "newyork-2": 3420.7
    }
   },
   "rank": 40,
   "pareto": false
  },
  {
   "id": "startlux-0.8b::cojevlight",
   "model": "startlux-0.8b",
   "mode": "cojevlight",
   "name": "StartLux 0.8B",
   "family": "startlux",
   "family_label": "StartLux",
   "color": "#3ddc84",
   "kind": "native",
   "hosted": false,
   "params_b": 0.8,
   "score": 44.69,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 736.017,
      "sd": 28.548,
      "score": 45.74
     },
     "awt": {
      "raw": 494.366,
      "sd": 31.584,
      "score": 31.54
     },
     "aql": {
      "raw": 825.137,
      "sd": 43.644,
      "score": 23.98
     }
    },
    "jinan-2": {
     "att": {
      "raw": 733.991,
      "sd": 16.913,
      "score": 46.56
     },
     "awt": {
      "raw": 484.431,
      "sd": 17.002,
      "score": 30.0
     },
     "aql": {
      "raw": 586.437,
      "sd": 20.168,
      "score": 24.75
     }
    },
    "jinan-3": {
     "att": {
      "raw": 692.338,
      "sd": 7.69,
      "score": 46.73
     },
     "awt": {
      "raw": 453.83,
      "sd": 12.047,
      "score": 30.94
     },
     "aql": {
      "raw": 676.798,
      "sd": 19.535,
      "score": 24.58
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 519.25,
      "sd": 10.593,
      "score": 72.15
     },
     "awt": {
      "raw": 210.437,
      "sd": 11.603,
      "score": 46.84
     },
     "aql": {
      "raw": 174.332,
      "sd": 9.612,
      "score": 41.73
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 522.033,
      "sd": 6.145,
      "score": 67.35
     },
     "awt": {
      "raw": 245.93,
      "sd": 10.588,
      "score": 49.31
     },
     "aql": {
      "raw": 383.26,
      "sd": 19.334,
      "score": 39.94
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1353.051,
      "sd": 35.11,
      "score": 48.46
     },
     "awt": {
      "raw": 963.818,
      "sd": 30.77,
      "score": 44.36
     },
     "aql": {
      "raw": 2070.801,
      "sd": 74.753,
      "score": 42.35
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1452.049,
      "sd": 16.374,
      "score": 61.85
     },
     "awt": {
      "raw": 1077.539,
      "sd": 8.682,
      "score": 58.18
     },
     "aql": {
      "raw": 2918.081,
      "sd": 42.831,
      "score": 61.26
     }
    }
   },
   "cost": {
    "gpu_seconds": 354.3,
    "serving_seconds": 120.6,
    "wall_seconds": 299.7,
    "tokens_per_task": 25404112,
    "decisions_per_task": 12032,
    "tokens_per_decision": 2111.4,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 121.5,
     "jinan-2": 116.0,
     "jinan-3": 119.6,
     "hangzhou-1": 116.4,
     "hangzhou-2": 120.6,
     "newyork-1": 925.9,
     "newyork-2": 960.1
    }
   },
   "rank": 41,
   "pareto": false
  },
  {
   "id": "agent-jev::cojevlight",
   "model": "agent-jev",
   "mode": "cojevlight",
   "name": "Agent-Jev",
   "family": "agent-jev",
   "family_label": "Agent-JEV",
   "color": "#e57373",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 40.79,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 628.326,
      "sd": 19.911,
      "score": 55.95
     },
     "awt": {
      "raw": 385.195,
      "sd": 21.339,
      "score": 39.39
     },
     "aql": {
      "raw": 664.085,
      "sd": 34.636,
      "score": 31.72
     }
    },
    "jinan-2": {
     "att": {
      "raw": 616.115,
      "sd": 6.919,
      "score": 57.11
     },
     "awt": {
      "raw": 363.896,
      "sd": 6.038,
      "score": 37.91
     },
     "aql": {
      "raw": 441.11,
      "sd": 7.299,
      "score": 33.2
     }
    },
    "jinan-3": {
     "att": {
      "raw": 591.419,
      "sd": 17.399,
      "score": 56.67
     },
     "awt": {
      "raw": 349.43,
      "sd": 16.508,
      "score": 38.59
     },
     "aql": {
      "raw": 532.568,
      "sd": 24.207,
      "score": 32.31
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 606.634,
      "sd": 22.685,
      "score": 61.83
     },
     "awt": {
      "raw": 296.201,
      "sd": 22.513,
      "score": 38.28
     },
     "aql": {
      "raw": 245.406,
      "sd": 18.649,
      "score": 32.36
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 533.297,
      "sd": 33.691,
      "score": 65.32
     },
     "awt": {
      "raw": 261.315,
      "sd": 37.888,
      "score": 47.01
     },
     "aql": {
      "raw": 414.43,
      "sd": 43.804,
      "score": 36.26
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1498.079,
      "sd": 10.864,
      "score": 36.14
     },
     "awt": {
      "raw": 1165.284,
      "sd": 11.812,
      "score": 31.88
     },
     "aql": {
      "raw": 2643.194,
      "sd": 13.752,
      "score": 21.85
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1665.718,
      "sd": 18.962,
      "score": 39.96
     },
     "awt": {
      "raw": 1346.561,
      "sd": 19.604,
      "score": 37.4
     },
     "aql": {
      "raw": 3835.581,
      "sd": 50.871,
      "score": 25.5
     }
    }
   },
   "cost": {
    "gpu_seconds": 1353.7,
    "serving_seconds": 486.3,
    "wall_seconds": 577.3,
    "tokens_per_task": null,
    "decisions_per_task": 12697,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 488.1,
     "jinan-2": 466.6,
     "jinan-3": 484.8,
     "hangzhou-1": 453.5,
     "hangzhou-2": 473.2,
     "newyork-1": 3510.8,
     "newyork-2": 3599.0
    }
   },
   "rank": 42,
   "pareto": false
  },
  {
   "id": "agent-jev::jevlight",
   "model": "agent-jev",
   "mode": "jevlight",
   "name": "Agent-Jev",
   "family": "agent-jev",
   "family_label": "Agent-JEV",
   "color": "#e57373",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 35.7,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 624.045,
      "sd": 22.696,
      "score": 56.39
     },
     "awt": {
      "raw": 375.823,
      "sd": 25.052,
      "score": 40.17
     },
     "aql": {
      "raw": 656.316,
      "sd": 43.244,
      "score": 32.14
     }
    },
    "jinan-2": {
     "att": {
      "raw": 605.54,
      "sd": 23.828,
      "score": 58.16
     },
     "awt": {
      "raw": 347.335,
      "sd": 22.823,
      "score": 39.2
     },
     "aql": {
      "raw": 421.048,
      "sd": 27.675,
      "score": 34.58
     }
    },
    "jinan-3": {
     "att": {
      "raw": 572.361,
      "sd": 12.58,
      "score": 58.74
     },
     "awt": {
      "raw": 329.265,
      "sd": 13.15,
      "score": 40.33
     },
     "aql": {
      "raw": 502.379,
      "sd": 20.074,
      "score": 34.19
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 620.8,
      "sd": 36.81,
      "score": 60.29
     },
     "awt": {
      "raw": 322.097,
      "sd": 44.903,
      "score": 36.18
     },
     "aql": {
      "raw": 261.98,
      "sd": 28.756,
      "score": 30.57
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 540.962,
      "sd": 2.404,
      "score": 63.97
     },
     "awt": {
      "raw": 277.877,
      "sd": 2.5,
      "score": 44.68
     },
     "aql": {
      "raw": 489.262,
      "sd": 5.517,
      "score": 28.45
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1676.876,
      "sd": 36.504,
      "score": 22.5
     },
     "awt": {
      "raw": 1423.345,
      "sd": 40.102,
      "score": 18.73
     },
     "aql": {
      "raw": 3189.182,
      "sd": 67.712,
      "score": 6.09
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1879.691,
      "sd": 6.476,
      "score": 20.69
     },
     "awt": {
      "raw": 1642.166,
      "sd": 7.383,
      "score": 18.89
     },
     "aql": {
      "raw": 4497.422,
      "sd": 8.84,
      "score": 4.67
     }
    }
   },
   "cost": {
    "gpu_seconds": 487.7,
    "serving_seconds": 138.9,
    "wall_seconds": 207.1,
    "tokens_per_task": null,
    "decisions_per_task": 13077,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 109.5,
     "jinan-2": 109.4,
     "jinan-3": 109.7,
     "hangzhou-1": 139.5,
     "hangzhou-2": 139.1,
     "newyork-1": 1387.2,
     "newyork-2": 1419.5
    }
   },
   "rank": 43,
   "pareto": false
  },
  {
   "id": "open-jev-2b::jevlight",
   "model": "open-jev-2b",
   "mode": "jevlight",
   "name": "Open-Jev 2B",
   "family": "open-jev",
   "family_label": "Open-JEV",
   "color": "#c792ea",
   "kind": "native",
   "hosted": false,
   "params_b": 2.0,
   "score": 32.82,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 563.273,
      "sd": 32.56,
      "score": 63.0
     },
     "awt": {
      "raw": 309.987,
      "sd": 25.541,
      "score": 46.23
     },
     "aql": {
      "raw": 541.086,
      "sd": 43.807,
      "score": 39.03
     }
    },
    "jinan-2": {
     "att": {
      "raw": 570.268,
      "sd": 23.163,
      "score": 61.78
     },
     "awt": {
      "raw": 303.939,
      "sd": 21.97,
      "score": 42.88
     },
     "aql": {
      "raw": 368.211,
      "sd": 26.283,
      "score": 38.56
     }
    },
    "jinan-3": {
     "att": {
      "raw": 500.631,
      "sd": 11.441,
      "score": 67.19
     },
     "awt": {
      "raw": 246.418,
      "sd": 11.528,
      "score": 48.81
     },
     "aql": {
      "raw": 375.92,
      "sd": 17.584,
      "score": 43.54
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 897.393,
      "sd": 26.308,
      "score": 35.83
     },
     "awt": {
      "raw": 604.487,
      "sd": 34.397,
      "score": 20.42
     },
     "aql": {
      "raw": 498.434,
      "sd": 26.689,
      "score": 12.94
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 628.957,
      "sd": 1.877,
      "score": 49.63
     },
     "awt": {
      "raw": 368.092,
      "sd": 9.02,
      "score": 34.0
     },
     "aql": {
      "raw": 607.159,
      "sd": 10.703,
      "score": 18.3
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1790.053,
      "sd": 15.795,
      "score": 14.6
     },
     "awt": {
      "raw": 1598.22,
      "sd": 20.189,
      "score": 11.11
     },
     "aql": {
      "raw": 3225.536,
      "sd": 19.101,
      "score": 5.14
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1952.918,
      "sd": 8.985,
      "score": 14.59
     },
     "awt": {
      "raw": 1768.248,
      "sd": 10.854,
      "score": 11.99
     },
     "aql": {
      "raw": 4326.891,
      "sd": 33.523,
      "score": 9.73
     }
    }
   },
   "cost": {
    "gpu_seconds": 1143.4,
    "serving_seconds": 451.9,
    "wall_seconds": null,
    "tokens_per_task": null,
    "decisions_per_task": 12837,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 451.9,
     "jinan-2": 451.7,
     "jinan-3": 452.7,
     "hangzhou-1": 445.1,
     "hangzhou-2": 445.8,
     "newyork-1": 2868.6,
     "newyork-2": 2887.7
    }
   },
   "rank": 44,
   "pareto": false
  },
  {
   "id": "von::cojevlight",
   "model": "von",
   "mode": "cojevlight",
   "name": "Von",
   "family": "von",
   "family_label": "Von",
   "color": "#81c784",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 31.85,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 719.572,
      "sd": 16.159,
      "score": 47.2
     },
     "awt": {
      "raw": 485.258,
      "sd": 14.785,
      "score": 32.12
     },
     "aql": {
      "raw": 762.632,
      "sd": 17.015,
      "score": 26.79
     }
    },
    "jinan-2": {
     "att": {
      "raw": 702.247,
      "sd": 10.655,
      "score": 49.22
     },
     "awt": {
      "raw": 455.627,
      "sd": 10.635,
      "score": 31.7
     },
     "aql": {
      "raw": 540.356,
      "sd": 12.446,
      "score": 27.18
     }
    },
    "jinan-3": {
     "att": {
      "raw": 730.182,
      "sd": 8.776,
      "score": 43.37
     },
     "awt": {
      "raw": 497.745,
      "sd": 11.493,
      "score": 28.23
     },
     "aql": {
      "raw": 692.834,
      "sd": 25.416,
      "score": 23.83
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 627.654,
      "sd": 7.535,
      "score": 59.56
     },
     "awt": {
      "raw": 323.749,
      "sd": 8.923,
      "score": 36.05
     },
     "aql": {
      "raw": 268.226,
      "sd": 7.391,
      "score": 29.92
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 562.717,
      "sd": 16.212,
      "score": 60.22
     },
     "awt": {
      "raw": 303.63,
      "sd": 17.366,
      "score": 41.31
     },
     "aql": {
      "raw": 488.006,
      "sd": 20.539,
      "score": 28.58
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1822.997,
      "sd": 12.39,
      "score": 12.39
     },
     "awt": {
      "raw": 1574.142,
      "sd": 13.775,
      "score": 12.11
     },
     "aql": {
      "raw": 2800.279,
      "sd": 12.844,
      "score": 17.01
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1964.206,
      "sd": 22.635,
      "score": 13.67
     },
     "awt": {
      "raw": 1716.254,
      "sd": 23.376,
      "score": 14.77
     },
     "aql": {
      "raw": 3607.189,
      "sd": 57.595,
      "score": 33.53
     }
    }
   },
   "cost": {
    "gpu_seconds": 3189.4,
    "serving_seconds": 1224.5,
    "wall_seconds": 1305.0,
    "tokens_per_task": 41274547,
    "decisions_per_task": 11868,
    "tokens_per_decision": 3477.7,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1268.7,
     "jinan-2": 1172.9,
     "jinan-3": 1224.5,
     "hangzhou-1": 1126.2,
     "hangzhou-2": 1178.0,
     "newyork-1": 8132.7,
     "newyork-2": 8223.1
    }
   },
   "rank": 45,
   "pareto": false
  },
  {
   "id": "bespoke-nimble-9b::cojevlight",
   "model": "bespoke-nimble-9b",
   "mode": "cojevlight",
   "name": "Bespoke-Nimble 9B",
   "family": "bespoke",
   "family_label": "Bespoke",
   "color": "#ba68c8",
   "kind": "native",
   "hosted": false,
   "params_b": 9.0,
   "score": 30.17,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 821.357,
      "sd": 44.171,
      "score": 38.67
     },
     "awt": {
      "raw": 602.545,
      "sd": 53.459,
      "score": 25.31
     },
     "aql": {
      "raw": 939.272,
      "sd": 63.699,
      "score": 19.36
     }
    },
    "jinan-2": {
     "att": {
      "raw": 823.027,
      "sd": 81.748,
      "score": 39.65
     },
     "awt": {
      "raw": 595.851,
      "sd": 95.086,
      "score": 24.28
     },
     "aql": {
      "raw": 686.085,
      "sd": 93.523,
      "score": 20.09
     }
    },
    "jinan-3": {
     "att": {
      "raw": 800.517,
      "sd": 34.18,
      "score": 37.56
     },
     "awt": {
      "raw": 584.799,
      "sd": 42.631,
      "score": 23.51
     },
     "aql": {
      "raw": 797.838,
      "sd": 55.521,
      "score": 19.28
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 706.311,
      "sd": 102.333,
      "score": 51.72
     },
     "awt": {
      "raw": 400.464,
      "sd": 99.377,
      "score": 30.73
     },
     "aql": {
      "raw": 329.576,
      "sd": 78.636,
      "score": 24.28
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 658.007,
      "sd": 77.1,
      "score": 45.34
     },
     "awt": {
      "raw": 407.397,
      "sd": 89.536,
      "score": 30.15
     },
     "aql": {
      "raw": 523.005,
      "sd": 53.66,
      "score": 25.32
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1457.768,
      "sd": 17.426,
      "score": 39.44
     },
     "awt": {
      "raw": 1173.342,
      "sd": 23.535,
      "score": 31.43
     },
     "aql": {
      "raw": 2719.784,
      "sd": 70.283,
      "score": 19.46
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1697.86,
      "sd": 13.289,
      "score": 36.91
     },
     "awt": {
      "raw": 1414.58,
      "sd": 19.563,
      "score": 32.8
     },
     "aql": {
      "raw": 4051.972,
      "sd": 53.315,
      "score": 18.32
     }
    }
   },
   "cost": {
    "gpu_seconds": 2970.3,
    "serving_seconds": 998.9,
    "wall_seconds": 1188.4,
    "tokens_per_task": null,
    "decisions_per_task": 11987,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 994.4,
     "jinan-2": 962.5,
     "jinan-3": 998.9,
     "hangzhou-1": 997.9,
     "hangzhou-2": 997.2,
     "newyork-1": 7807.3,
     "newyork-2": 8033.8
    }
   },
   "rank": 46,
   "pareto": false
  },
  {
   "id": "open-jev-2b::cojevlight",
   "model": "open-jev-2b",
   "mode": "cojevlight",
   "name": "Open-Jev 2B",
   "family": "open-jev",
   "family_label": "Open-JEV",
   "color": "#c792ea",
   "kind": "native",
   "hosted": false,
   "params_b": 2.0,
   "score": 29.5,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 810.018,
      "sd": 23.506,
      "score": 39.56
     },
     "awt": {
      "raw": 593.145,
      "sd": 23.958,
      "score": 25.8
     },
     "aql": {
      "raw": 992.235,
      "sd": 41.429,
      "score": 17.4
     }
    },
    "jinan-2": {
     "att": {
      "raw": 833.89,
      "sd": 33.77,
      "score": 38.86
     },
     "awt": {
      "raw": 604.738,
      "sd": 35.49,
      "score": 23.87
     },
     "aql": {
      "raw": 728.836,
      "sd": 42.616,
      "score": 18.29
     }
    },
    "jinan-3": {
     "att": {
      "raw": 778.17,
      "sd": 5.675,
      "score": 39.35
     },
     "awt": {
      "raw": 559.194,
      "sd": 7.654,
      "score": 24.82
     },
     "aql": {
      "raw": 821.359,
      "sd": 11.918,
      "score": 18.34
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 672.812,
      "sd": 15.191,
      "score": 54.95
     },
     "awt": {
      "raw": 377.445,
      "sd": 14.582,
      "score": 32.21
     },
     "aql": {
      "raw": 312.72,
      "sd": 12.089,
      "score": 25.71
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 553.546,
      "sd": 11.053,
      "score": 61.78
     },
     "awt": {
      "raw": 295.893,
      "sd": 17.777,
      "score": 42.29
     },
     "aql": {
      "raw": 484.252,
      "sd": 14.404,
      "score": 28.94
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1757.768,
      "sd": 14.421,
      "score": 16.8
     },
     "awt": {
      "raw": 1513.725,
      "sd": 16.603,
      "score": 14.68
     },
     "aql": {
      "raw": 2713.94,
      "sd": 3.583,
      "score": 19.64
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1852.0,
      "sd": 27.908,
      "score": 23.05
     },
     "awt": {
      "raw": 1612.26,
      "sd": 28.896,
      "score": 20.6
     },
     "aql": {
      "raw": 3633.471,
      "sd": 45.329,
      "score": 32.58
     }
    }
   },
   "cost": {
    "gpu_seconds": 2752.1,
    "serving_seconds": 1489.6,
    "wall_seconds": null,
    "tokens_per_task": null,
    "decisions_per_task": 12096,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1510.4,
     "jinan-2": 1469.6,
     "jinan-3": 1489.6,
     "hangzhou-1": 1124.8,
     "hangzhou-2": 1152.0,
     "newyork-1": 6074.4,
     "newyork-2": 6443.6
    }
   },
   "rank": 47,
   "pareto": false
  },
  {
   "id": "valen-0.8b::cojevlight",
   "model": "valen-0.8b",
   "mode": "cojevlight",
   "name": "Valen 0.8B",
   "family": "valen",
   "family_label": "Valen",
   "color": "#6cb6ff",
   "kind": "native",
   "hosted": false,
   "params_b": 0.8,
   "score": 29.14,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 1038.233,
      "sd": 37.412,
      "score": 23.55
     },
     "awt": {
      "raw": 845.995,
      "sd": 53.404,
      "score": 14.63
     },
     "aql": {
      "raw": 1340.922,
      "sd": 66.363,
      "score": 6.66
     }
    },
    "jinan-2": {
     "att": {
      "raw": 1027.031,
      "sd": 35.267,
      "score": 26.29
     },
     "awt": {
      "raw": 808.065,
      "sd": 41.927,
      "score": 15.87
     },
     "aql": {
      "raw": 957.018,
      "sd": 42.35,
      "score": 10.21
     }
    },
    "jinan-3": {
     "att": {
      "raw": 1001.769,
      "sd": 28.12,
      "score": 23.4
     },
     "awt": {
      "raw": 818.003,
      "sd": 32.121,
      "score": 13.69
     },
     "aql": {
      "raw": 1175.734,
      "sd": 49.384,
      "score": 6.78
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 648.59,
      "sd": 57.92,
      "score": 57.38
     },
     "awt": {
      "raw": 347.901,
      "sd": 57.505,
      "score": 34.25
     },
     "aql": {
      "raw": 283.206,
      "sd": 54.49,
      "score": 28.43
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 560.007,
      "sd": 2.121,
      "score": 60.67
     },
     "awt": {
      "raw": 309.88,
      "sd": 2.343,
      "score": 40.54
     },
     "aql": {
      "raw": 527.147,
      "sd": 15.719,
      "score": 24.95
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1365.64,
      "sd": 14.149,
      "score": 47.34
     },
     "awt": {
      "raw": 1042.79,
      "sd": 16.546,
      "score": 39.19
     },
     "aql": {
      "raw": 2470.997,
      "sd": 37.606,
      "score": 27.51
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1622.737,
      "sd": 47.664,
      "score": 44.13
     },
     "awt": {
      "raw": 1328.956,
      "sd": 53.848,
      "score": 38.63
     },
     "aql": {
      "raw": 3768.862,
      "sd": 129.961,
      "score": 27.79
     }
    }
   },
   "cost": {
    "gpu_seconds": 2249.9,
    "serving_seconds": 749.4,
    "wall_seconds": 871.5,
    "tokens_per_task": 24116774,
    "decisions_per_task": 11678,
    "tokens_per_decision": 2065.1,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 695.1,
     "jinan-2": 692.7,
     "jinan-3": 725.5,
     "hangzhou-1": 738.0,
     "hangzhou-2": 805.0,
     "newyork-1": 6044.0,
     "newyork-2": 6048.7
    }
   },
   "rank": 48,
   "pareto": false
  },
  {
   "id": "von::jevlight",
   "model": "von",
   "mode": "jevlight",
   "name": "Von",
   "family": "von",
   "family_label": "Von",
   "color": "#81c784",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 27.58,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 610.76,
      "sd": 14.46,
      "score": 57.78
     },
     "awt": {
      "raw": 343.895,
      "sd": 11.541,
      "score": 42.96
     },
     "aql": {
      "raw": 592.268,
      "sd": 18.083,
      "score": 35.8
     }
    },
    "jinan-2": {
     "att": {
      "raw": 648.783,
      "sd": 21.614,
      "score": 54.0
     },
     "awt": {
      "raw": 378.727,
      "sd": 25.1,
      "score": 36.81
     },
     "aql": {
      "raw": 459.052,
      "sd": 30.428,
      "score": 32.02
     }
    },
    "jinan-3": {
     "att": {
      "raw": 568.362,
      "sd": 29.428,
      "score": 59.18
     },
     "awt": {
      "raw": 323.465,
      "sd": 37.03,
      "score": 40.85
     },
     "aql": {
      "raw": 487.893,
      "sd": 48.759,
      "score": 35.13
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 1037.236,
      "sd": 61.897,
      "score": 26.21
     },
     "awt": {
      "raw": 779.487,
      "sd": 66.332,
      "score": 14.06
     },
     "aql": {
      "raw": 630.684,
      "sd": 32.93,
      "score": 6.49
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 761.529,
      "sd": 10.147,
      "score": 31.44
     },
     "awt": {
      "raw": 542.508,
      "sd": 11.573,
      "score": 19.27
     },
     "aql": {
      "raw": 832.707,
      "sd": 6.189,
      "score": 3.44
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1873.114,
      "sd": 7.216,
      "score": 9.11
     },
     "awt": {
      "raw": 1692.409,
      "sd": 7.938,
      "score": 7.34
     },
     "aql": {
      "raw": 2814.48,
      "sd": 6.099,
      "score": 16.58
     }
    },
    "newyork-2": {
     "att": {
      "raw": 2010.998,
      "sd": 7.447,
      "score": 9.92
     },
     "awt": {
      "raw": 1823.068,
      "sd": 7.599,
      "score": 9.14
     },
     "aql": {
      "raw": 3661.188,
      "sd": 20.723,
      "score": 31.58
     }
    }
   },
   "cost": {
    "gpu_seconds": 751.3,
    "serving_seconds": 225.9,
    "wall_seconds": 302.9,
    "tokens_per_task": 18002833,
    "decisions_per_task": 12498,
    "tokens_per_decision": 1440.4,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 173.7,
     "jinan-2": 174.1,
     "jinan-3": 173.3,
     "hangzhou-1": 226.6,
     "hangzhou-2": 225.9,
     "newyork-1": 2135.8,
     "newyork-2": 2149.7
    }
   },
   "rank": 49,
   "pareto": false
  },
  {
   "id": "valen-2b::cojevlight",
   "model": "valen-2b",
   "mode": "cojevlight",
   "name": "Valen 2B",
   "family": "valen",
   "family_label": "Valen",
   "color": "#6cb6ff",
   "kind": "native",
   "hosted": false,
   "params_b": 2.0,
   "score": 25.79,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 1058.66,
      "sd": 10.912,
      "score": 22.29
     },
     "awt": {
      "raw": 867.39,
      "sd": 11.69,
      "score": 13.84
     },
     "aql": {
      "raw": 1255.13,
      "sd": 37.77,
      "score": 9.02
     }
    },
    "jinan-2": {
     "att": {
      "raw": 979.817,
      "sd": 31.793,
      "score": 29.13
     },
     "awt": {
      "raw": 754.893,
      "sd": 34.489,
      "score": 17.75
     },
     "aql": {
      "raw": 815.076,
      "sd": 41.402,
      "score": 14.97
     }
    },
    "jinan-3": {
     "att": {
      "raw": 1027.294,
      "sd": 46.144,
      "score": 21.82
     },
     "awt": {
      "raw": 835.119,
      "sd": 51.486,
      "score": 13.08
     },
     "aql": {
      "raw": 1059.151,
      "sd": 61.309,
      "score": 10.14
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 698.961,
      "sd": 45.988,
      "score": 52.42
     },
     "awt": {
      "raw": 395.101,
      "sd": 52.663,
      "score": 31.07
     },
     "aql": {
      "raw": 327.36,
      "sd": 43.641,
      "score": 24.46
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 598.007,
      "sd": 15.232,
      "score": 54.43
     },
     "awt": {
      "raw": 360.492,
      "sd": 19.71,
      "score": 34.79
     },
     "aql": {
      "raw": 535.396,
      "sd": 16.123,
      "score": 24.22
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1629.241,
      "sd": 4.772,
      "score": 25.99
     },
     "awt": {
      "raw": 1333.379,
      "sd": 10.307,
      "score": 23.02
     },
     "aql": {
      "raw": 2607.761,
      "sd": 30.963,
      "score": 22.99
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1782.158,
      "sd": 37.599,
      "score": 29.18
     },
     "awt": {
      "raw": 1497.891,
      "sd": 33.631,
      "score": 27.47
     },
     "aql": {
      "raw": 3446.414,
      "sd": 62.962,
      "score": 39.49
     }
    }
   },
   "cost": {
    "gpu_seconds": 1769.2,
    "serving_seconds": 635.6,
    "wall_seconds": null,
    "tokens_per_task": 23351247,
    "decisions_per_task": 11366,
    "tokens_per_decision": 2054.6,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 635.6,
     "jinan-2": 610.8,
     "jinan-3": 619.2,
     "hangzhou-1": 629.3,
     "hangzhou-2": 657.6,
     "newyork-1": 4535.9,
     "newyork-2": 4696.3
    }
   },
   "rank": 50,
   "pareto": false
  },
  {
   "id": "valen-2b::jevlight",
   "model": "valen-2b",
   "mode": "jevlight",
   "name": "Valen 2B",
   "family": "valen",
   "family_label": "Valen",
   "color": "#6cb6ff",
   "kind": "native",
   "hosted": false,
   "params_b": 2.0,
   "score": 12.94,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 1197.574,
      "sd": 66.254,
      "score": 14.34
     },
     "awt": {
      "raw": 1017.813,
      "sd": 71.812,
      "score": 8.81
     },
     "aql": {
      "raw": 1455.417,
      "sd": 78.08,
      "score": 3.74
     }
    },
    "jinan-2": {
     "att": {
      "raw": 1209.465,
      "sd": 44.695,
      "score": 16.43
     },
     "awt": {
      "raw": 1013.237,
      "sd": 48.061,
      "score": 9.61
     },
     "aql": {
      "raw": 1066.655,
      "sd": 51.268,
      "score": 6.99
     }
    },
    "jinan-3": {
     "att": {
      "raw": 1168.143,
      "sd": 36.767,
      "score": 13.7
     },
     "awt": {
      "raw": 987.105,
      "sd": 41.138,
      "score": 8.19
     },
     "aql": {
      "raw": 1231.333,
      "sd": 62.079,
      "score": 5.29
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 975.647,
      "sd": 20.804,
      "score": 30.28
     },
     "awt": {
      "raw": 739.173,
      "sd": 30.458,
      "score": 15.39
     },
     "aql": {
      "raw": 550.777,
      "sd": 17.127,
      "score": 10.2
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 703.703,
      "sd": 9.965,
      "score": 38.95
     },
     "awt": {
      "raw": 479.886,
      "sd": 18.283,
      "score": 23.93
     },
     "aql": {
      "raw": 740.232,
      "sd": 11.035,
      "score": 8.98
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1859.858,
      "sd": 11.641,
      "score": 9.97
     },
     "awt": {
      "raw": 1655.782,
      "sd": 10.202,
      "score": 8.78
     },
     "aql": {
      "raw": 3151.989,
      "sd": 13.553,
      "score": 7.07
     }
    },
    "newyork-2": {
     "att": {
      "raw": 2011.535,
      "sd": 39.408,
      "score": 9.88
     },
     "awt": {
      "raw": 1823.377,
      "sd": 44.704,
      "score": 9.13
     },
     "aql": {
      "raw": 4246.468,
      "sd": 137.652,
      "score": 12.18
     }
    }
   },
   "cost": {
    "gpu_seconds": 419.2,
    "serving_seconds": 408.8,
    "wall_seconds": null,
    "tokens_per_task": 10649526,
    "decisions_per_task": 12466,
    "tokens_per_decision": 854.3,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 409.0,
     "jinan-2": 407.4,
     "jinan-3": 408.6,
     "hangzhou-1": 408.3,
     "hangzhou-2": 407.1,
     "newyork-1": 449.5,
     "newyork-2": 444.7
    }
   },
   "rank": 51,
   "pareto": false
  },
  {
   "id": "valen-0.8b::jevlight",
   "model": "valen-0.8b",
   "mode": "jevlight",
   "name": "Valen 0.8B",
   "family": "valen",
   "family_label": "Valen",
   "color": "#6cb6ff",
   "kind": "native",
   "hosted": false,
   "params_b": 0.8,
   "score": 12.11,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 1053.286,
      "sd": 46.877,
      "score": 22.62
     },
     "awt": {
      "raw": 853.851,
      "sd": 58.685,
      "score": 14.34
     },
     "aql": {
      "raw": 1364.062,
      "sd": 74.209,
      "score": 6.05
     }
    },
    "jinan-2": {
     "att": {
      "raw": 1194.56,
      "sd": 18.19,
      "score": 17.18
     },
     "awt": {
      "raw": 999.83,
      "sd": 19.682,
      "score": 9.98
     },
     "aql": {
      "raw": 1152.35,
      "sd": 21.348,
      "score": 4.69
     }
    },
    "jinan-3": {
     "att": {
      "raw": 1102.377,
      "sd": 25.026,
      "score": 17.36
     },
     "awt": {
      "raw": 905.458,
      "sd": 36.554,
      "score": 10.71
     },
     "aql": {
      "raw": 1251.136,
      "sd": 5.245,
      "score": 4.77
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 1062.869,
      "sd": 38.746,
      "score": 24.59
     },
     "awt": {
      "raw": 815.573,
      "sd": 55.947,
      "score": 12.93
     },
     "aql": {
      "raw": 641.564,
      "sd": 45.667,
      "score": 6.02
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 773.789,
      "sd": 48.407,
      "score": 29.92
     },
     "awt": {
      "raw": 541.596,
      "sd": 55.201,
      "score": 19.34
     },
     "aql": {
      "raw": 801.067,
      "sd": 55.018,
      "score": 5.27
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1785.768,
      "sd": 24.876,
      "score": 14.89
     },
     "awt": {
      "raw": 1614.267,
      "sd": 25.726,
      "score": 10.45
     },
     "aql": {
      "raw": 3429.019,
      "sd": 68.723,
      "score": 0.0
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1972.266,
      "sd": 32.696,
      "score": 13.02
     },
     "awt": {
      "raw": 1801.084,
      "sd": 35.265,
      "score": 10.28
     },
     "aql": {
      "raw": 4661.039,
      "sd": 36.044,
      "score": 0.0
     }
    }
   },
   "cost": {
    "gpu_seconds": 855.9,
    "serving_seconds": 264.9,
    "wall_seconds": 352.1,
    "tokens_per_task": 10480132,
    "decisions_per_task": 12268,
    "tokens_per_decision": 854.3,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 206.1,
     "jinan-2": 205.4,
     "jinan-3": 205.1,
     "hangzhou-1": 266.5,
     "hangzhou-2": 264.9,
     "newyork-1": 2396.1,
     "newyork-2": 2447.0
    }
   },
   "rank": 52,
   "pareto": false
  },
  {
   "id": "gliner2.5-decide::jevlight",
   "model": "gliner2.5-decide",
   "mode": "jevlight",
   "name": "GLiNER2.5-Decide",
   "family": "gliner",
   "family_label": "GLiNER",
   "color": "#4fc3f7",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 9.99,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 1224.6,
      "sd": 0.365,
      "score": 12.9
     },
     "awt": {
      "raw": 1057.407,
      "sd": 0.773,
      "score": 7.61
     },
     "aql": {
      "raw": 1560.206,
      "sd": 1.001,
      "score": 1.26
     }
    },
    "jinan-2": {
     "att": {
      "raw": 1287.624,
      "sd": 0.537,
      "score": 12.66
     },
     "awt": {
      "raw": 1117.868,
      "sd": 0.302,
      "score": 6.9
     },
     "aql": {
      "raw": 1281.387,
      "sd": 0.165,
      "score": 1.54
     }
    },
    "jinan-3": {
     "att": {
      "raw": 1198.677,
      "sd": 0.266,
      "score": 12.08
     },
     "awt": {
      "raw": 1032.949,
      "sd": 0.627,
      "score": 6.86
     },
     "aql": {
      "raw": 1406.38,
      "sd": 0.859,
      "score": 1.0
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 1057.432,
      "sd": 0.642,
      "score": 24.93
     },
     "awt": {
      "raw": 813.966,
      "sd": 0.248,
      "score": 12.97
     },
     "aql": {
      "raw": 651.172,
      "sd": 0.196,
      "score": 5.62
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 722.558,
      "sd": 0.152,
      "score": 36.44
     },
     "awt": {
      "raw": 496.138,
      "sd": 0.382,
      "score": 22.67
     },
     "aql": {
      "raw": 821.586,
      "sd": 0.806,
      "score": 4.08
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1986.931,
      "sd": 0.853,
      "score": 1.97
     },
     "awt": {
      "raw": 1859.564,
      "sd": 0.912,
      "score": 1.15
     },
     "aql": {
      "raw": 2977.058,
      "sd": 0.892,
      "score": 11.87
     }
    },
    "newyork-2": {
     "att": {
      "raw": 2140.076,
      "sd": 0.234,
      "score": 0.0
     },
     "awt": {
      "raw": 2010.879,
      "sd": 0.579,
      "score": 0.0
     },
     "aql": {
      "raw": 3844.059,
      "sd": 0.231,
      "score": 25.21
     }
    }
   },
   "cost": {
    "gpu_seconds": 917.0,
    "serving_seconds": 221.6,
    "wall_seconds": 459.8,
    "tokens_per_task": null,
    "decisions_per_task": 12624,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 178.8,
     "jinan-2": 179.0,
     "jinan-3": 219.5,
     "hangzhou-1": 1241.4,
     "hangzhou-2": 221.6,
     "newyork-1": 2168.5,
     "newyork-2": 2210.0
    }
   },
   "rank": 53,
   "pareto": false
  },
  {
   "id": "gliner2.5-decide::cojevlight",
   "model": "gliner2.5-decide",
   "mode": "cojevlight",
   "name": "GLiNER2.5-Decide",
   "family": "gliner",
   "family_label": "GLiNER",
   "color": "#4fc3f7",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 8.52,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 1258.768,
      "sd": 33.617,
      "score": 11.12
     },
     "awt": {
      "raw": 1091.014,
      "sd": 35.477,
      "score": 6.62
     },
     "aql": {
      "raw": 1556.928,
      "sd": 36.501,
      "score": 1.33
     }
    },
    "jinan-2": {
     "att": {
      "raw": 1274.855,
      "sd": 7.733,
      "score": 13.26
     },
     "awt": {
      "raw": 1104.654,
      "sd": 8.781,
      "score": 7.23
     },
     "aql": {
      "raw": 1265.874,
      "sd": 9.975,
      "score": 1.9
     }
    },
    "jinan-3": {
     "att": {
      "raw": 1270.098,
      "sd": 4.887,
      "score": 8.42
     },
     "awt": {
      "raw": 1106.907,
      "sd": 5.716,
      "score": 4.83
     },
     "aql": {
      "raw": 1450.806,
      "sd": 7.323,
      "score": 0.0
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 1057.432,
      "sd": 0.642,
      "score": 24.93
     },
     "awt": {
      "raw": 813.966,
      "sd": 0.248,
      "score": 12.97
     },
     "aql": {
      "raw": 651.172,
      "sd": 0.196,
      "score": 5.62
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 743.741,
      "sd": 19.334,
      "score": 33.69
     },
     "awt": {
      "raw": 521.486,
      "sd": 26.166,
      "score": 20.77
     },
     "aql": {
      "raw": 842.691,
      "sd": 19.66,
      "score": 2.88
     }
    },
    "newyork-1": {
     "att": {
      "raw": 2019.613,
      "sd": 2.889,
      "score": 0.0
     },
     "awt": {
      "raw": 1892.348,
      "sd": 3.019,
      "score": 0.0
     },
     "aql": {
      "raw": 3174.215,
      "sd": 8.156,
      "score": 6.48
     }
    },
    "newyork-2": {
     "att": {
      "raw": 2137.176,
      "sd": 30.562,
      "score": 0.22
     },
     "awt": {
      "raw": 2007.067,
      "sd": 30.363,
      "score": 0.18
     },
     "aql": {
      "raw": 4108.887,
      "sd": 60.461,
      "score": 16.49
     }
    }
   },
   "cost": {
    "gpu_seconds": 3998.2,
    "serving_seconds": 1410.9,
    "wall_seconds": 2513.6,
    "tokens_per_task": null,
    "decisions_per_task": 12653,
    "tokens_per_decision": null,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 1410.9,
     "jinan-2": 1333.3,
     "jinan-3": 1847.0,
     "hangzhou-1": 1274.5,
     "hangzhou-2": 1330.3,
     "newyork-1": 10290.0,
     "newyork-2": 10501.2
    }
   },
   "rank": 54,
   "pareto": false
  },
  {
   "id": "laya-multilingual::cojevlight",
   "model": "laya-multilingual",
   "mode": "cojevlight",
   "name": "Laya Multilingual",
   "family": "laya",
   "family_label": "Laya",
   "color": "#ffd54f",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 2.01,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 1459.517,
      "sd": 18.489,
      "score": 1.58
     },
     "awt": {
      "raw": 1304.029,
      "sd": 19.089,
      "score": 1.01
     },
     "aql": {
      "raw": 1575.63,
      "sd": 19.935,
      "score": 0.91
     }
    },
    "jinan-2": {
     "att": {
      "raw": 1565.454,
      "sd": 4.44,
      "score": 0.87
     },
     "awt": {
      "raw": 1407.282,
      "sd": 5.773,
      "score": 0.54
     },
     "aql": {
      "raw": 1327.837,
      "sd": 6.049,
      "score": 0.49
     }
    },
    "jinan-3": {
     "att": {
      "raw": 1415.332,
      "sd": 2.725,
      "score": 1.59
     },
     "awt": {
      "raw": 1263.541,
      "sd": 3.349,
      "score": 0.96
     },
     "aql": {
      "raw": 1395.985,
      "sd": 5.665,
      "score": 1.24
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 1531.434,
      "sd": 5.086,
      "score": 0.34
     },
     "awt": {
      "raw": 1357.252,
      "sd": 7.591,
      "score": 0.18
     },
     "aql": {
      "raw": 794.614,
      "sd": 2.9,
      "score": 0.16
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 1055.878,
      "sd": 10.303,
      "score": 0.36
     },
     "awt": {
      "raw": 894.426,
      "sd": 9.764,
      "score": 0.29
     },
     "aql": {
      "raw": 890.958,
      "sd": 12.154,
      "score": 0.26
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1964.5,
      "sd": 1.09,
      "score": 3.35
     },
     "awt": {
      "raw": 1850.904,
      "sd": 1.112,
      "score": 1.46
     },
     "aql": {
      "raw": 3204.188,
      "sd": 9.51,
      "score": 5.69
     }
    },
    "newyork-2": {
     "att": {
      "raw": 2064.27,
      "sd": 4.69,
      "score": 5.75
     },
     "awt": {
      "raw": 1955.089,
      "sd": 4.262,
      "score": 2.62
     },
     "aql": {
      "raw": 4232.54,
      "sd": 4.831,
      "score": 12.61
     }
    }
   },
   "cost": {
    "gpu_seconds": 133.8,
    "serving_seconds": 137.0,
    "wall_seconds": 318.2,
    "tokens_per_task": 28580063,
    "decisions_per_task": 13357,
    "tokens_per_decision": 2139.6,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 129.4,
     "jinan-2": 138.4,
     "jinan-3": 138.4,
     "hangzhou-1": 113.8,
     "hangzhou-2": 117.4,
     "newyork-1": 148.2,
     "newyork-2": 150.9
    }
   },
   "rank": 55,
   "pareto": true
  },
  {
   "id": "laya-multilingual::jevlight",
   "model": "laya-multilingual",
   "mode": "jevlight",
   "name": "Laya Multilingual",
   "family": "laya",
   "family_label": "Laya",
   "color": "#ffd54f",
   "kind": "native",
   "hosted": false,
   "params_b": null,
   "score": 1.84,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 1495.624,
      "sd": 0.544,
      "score": 0.0
     },
     "awt": {
      "raw": 1346.542,
      "sd": 0.612,
      "score": 0.0
     },
     "aql": {
      "raw": 1616.17,
      "sd": 0.711,
      "score": 0.0
     }
    },
    "jinan-2": {
     "att": {
      "raw": 1588.264,
      "sd": 1.899,
      "score": 0.0
     },
     "awt": {
      "raw": 1434.838,
      "sd": 1.614,
      "score": 0.0
     },
     "aql": {
      "raw": 1349.765,
      "sd": 0.574,
      "score": 0.0
     }
    },
    "jinan-3": {
     "att": {
      "raw": 1451.385,
      "sd": 0.152,
      "score": 0.0
     },
     "awt": {
      "raw": 1305.565,
      "sd": 0.376,
      "score": 0.0
     },
     "aql": {
      "raw": 1436.354,
      "sd": 0.534,
      "score": 0.32
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 1539.367,
      "sd": 0.17,
      "score": 0.0
     },
     "awt": {
      "raw": 1366.775,
      "sd": 0.848,
      "score": 0.0
     },
     "aql": {
      "raw": 799.298,
      "sd": 0.304,
      "score": 0.0
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 1059.851,
      "sd": 0.779,
      "score": 0.0
     },
     "awt": {
      "raw": 901.234,
      "sd": 0.291,
      "score": 0.0
     },
     "aql": {
      "raw": 895.975,
      "sd": 0.24,
      "score": 0.0
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1980.249,
      "sd": 0.19,
      "score": 2.38
     },
     "awt": {
      "raw": 1869.335,
      "sd": 0.472,
      "score": 0.8
     },
     "aql": {
      "raw": 3044.102,
      "sd": 0.825,
      "score": 10.0
     }
    },
    "newyork-2": {
     "att": {
      "raw": 2076.098,
      "sd": 1.232,
      "score": 4.84
     },
     "awt": {
      "raw": 1969.79,
      "sd": 1.13,
      "score": 1.93
     },
     "aql": {
      "raw": 4047.579,
      "sd": 0.549,
      "score": 18.46
     }
    }
   },
   "cost": {
    "gpu_seconds": 194.5,
    "serving_seconds": 65.3,
    "wall_seconds": 210.4,
    "tokens_per_task": 12154074,
    "decisions_per_task": 13275,
    "tokens_per_decision": 915.5,
    "gpus": 1,
    "hosted": false,
    "runs": 21,
    "by_flow": {
     "jinan-1": 66.2,
     "jinan-2": 63.1,
     "jinan-3": 37.2,
     "hangzhou-1": 53.7,
     "hangzhou-2": 65.4,
     "newyork-1": 535.5,
     "newyork-2": 540.4
    }
   },
   "rank": 56,
   "pareto": false
  }
 ],
 "pareto": [
  "laya-multilingual::cojevlight",
  "startlux-0.8b::jevlight",
  "startlux-2b::jevlight",
  "startlux-4b::jevlight",
  "startlux-9b::jevlight",
  "clef-flash::cojevlight",
  "d3-flash::cojevlight"
 ],
 "baseline": {
  "id": "maxpressure",
  "name": "MaxPressure",
  "score": 73.81,
  "cells": {
   "jinan-1": {
    "att": {
     "raw": 345.208,
     "score": 94.59
    },
    "awt": {
     "raw": 88.23,
     "score": 85.78
    },
    "aql": {
     "raw": 154.033,
     "score": 83.84
    }
   },
   "jinan-2": {
    "att": {
     "raw": 329.334,
     "score": 94.89
    },
    "awt": {
     "raw": 67.032,
     "score": 84.65
    },
    "aql": {
     "raw": 81.141,
     "score": 83.46
    }
   },
   "jinan-3": {
    "att": {
     "raw": 323.672,
     "score": 94.72
    },
    "awt": {
     "raw": 71.833,
     "score": 84.9
    },
    "aql": {
     "raw": 109.436,
     "score": 83.32
    }
   },
   "hangzhou-1": {
    "att": {
     "raw": 383.547,
     "score": 92.26
    },
    "awt": {
     "raw": 69.948,
     "score": 74.41
    },
    "aql": {
     "raw": 57.907,
     "score": 71.93
    }
   },
   "hangzhou-2": {
    "att": {
     "raw": 435.657,
     "score": 84.56
    },
    "awt": {
     "raw": 140.697,
     "score": 70.52
    },
    "aql": {
     "raw": 244.88,
     "score": 61.01
    }
   },
   "newyork-1": {
    "att": {
     "raw": 1188.417,
     "score": 64.15
    },
    "awt": {
     "raw": 806.233,
     "score": 56.1
    },
    "aql": {
     "raw": 2058.528,
     "score": 42.85
    }
   },
   "newyork-2": {
    "att": {
     "raw": 1506.699,
     "score": 55.96
    },
    "awt": {
     "raw": 1149.194,
     "score": 52.18
    },
    "aql": {
     "raw": 3596.211,
     "score": 33.93
    }
   }
  }
 },
 "traditional": [
  {
   "id": "colight",
   "name": "CoLight",
   "mode": "baseline",
   "score": 84.83,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 325.147,
      "sd": 2.051,
      "score": 98.45
     },
     "awt": {
      "raw": 66.301,
      "sd": 1.433,
      "score": 94.77
     },
     "aql": {
      "raw": 115.647,
      "sd": 2.501,
      "score": 94.06
     }
    },
    "jinan-2": {
     "att": {
      "raw": 318.281,
      "sd": 1.096,
      "score": 96.95
     },
     "awt": {
      "raw": 55.034,
      "sd": 0.33,
      "score": 90.1
     },
     "aql": {
      "raw": 66.57,
      "sd": 0.4,
      "score": 89.34
     }
    },
    "jinan-3": {
     "att": {
      "raw": 309.22,
      "sd": 1.163,
      "score": 97.61
     },
     "awt": {
      "raw": 55.633,
      "sd": 0.577,
      "score": 92.38
     },
     "aql": {
      "raw": 84.677,
      "sd": 0.872,
      "score": 91.59
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 356.045,
      "sd": 0.812,
      "score": 97.2
     },
     "awt": {
      "raw": 39.579,
      "sd": 0.214,
      "score": 88.66
     },
     "aql": {
      "raw": 32.728,
      "sd": 0.179,
      "score": 87.56
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 481.357,
      "sd": 19.316,
      "score": 75.07
     },
     "awt": {
      "raw": 211.367,
      "sd": 15.385,
      "score": 55.06
     },
     "aql": {
      "raw": 298.494,
      "sd": 12.522,
      "score": 51.7
     }
    },
    "newyork-1": {
     "att": {
      "raw": 963.928,
      "sd": 4.171,
      "score": 89.48
     },
     "awt": {
      "raw": 518.119,
      "sd": 8.647,
      "score": 85.18
     },
     "aql": {
      "raw": 1338.372,
      "sd": 14.182,
      "score": 79.0
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1268.834,
      "sd": 17.12,
      "score": 83.36
     },
     "awt": {
      "raw": 884.822,
      "sd": 31.567,
      "score": 76.56
     },
     "aql": {
      "raw": 2784.077,
      "sd": 71.07,
      "score": 67.41
     }
    }
   },
   "cost": {
    "gpu_seconds": 238.1,
    "wall_seconds": 80.4,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 80.4,
     "jinan-2": 70.3,
     "jinan-3": 70.3,
     "hangzhou-1": 70.3,
     "hangzhou-2": 90.4,
     "newyork-1": 582.2,
     "newyork-2": 702.7
    }
   },
   "rank": 1
  },
  {
   "id": "citylight",
   "name": "CityLight",
   "mode": "baseline",
   "score": 81.8,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 342.042,
      "sd": 0.641,
      "score": 95.18
     },
     "awt": {
      "raw": 78.86,
      "sd": 0.125,
      "score": 89.31
     },
     "aql": {
      "raw": 137.624,
      "sd": 0.215,
      "score": 87.86
     }
    },
    "jinan-2": {
     "att": {
      "raw": 329.783,
      "sd": 2.19,
      "score": 94.81
     },
     "awt": {
      "raw": 64.089,
      "sd": 1.119,
      "score": 85.9
     },
     "aql": {
      "raw": 77.557,
      "sd": 1.341,
      "score": 84.8
     }
    },
    "jinan-3": {
     "att": {
      "raw": 322.813,
      "sd": 0.607,
      "score": 94.89
     },
     "awt": {
      "raw": 66.128,
      "sd": 0.636,
      "score": 87.32
     },
     "aql": {
      "raw": 100.702,
      "sd": 0.969,
      "score": 86.01
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 360.483,
      "sd": 0.944,
      "score": 96.38
     },
     "awt": {
      "raw": 40.818,
      "sd": 0.48,
      "score": 87.89
     },
     "aql": {
      "raw": 33.756,
      "sd": 0.397,
      "score": 86.71
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 405.446,
      "sd": 9.904,
      "score": 91.39
     },
     "awt": {
      "raw": 111.156,
      "sd": 12.569,
      "score": 79.47
     },
     "aql": {
      "raw": 196.402,
      "sd": 24.18,
      "score": 71.38
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1114.457,
      "sd": 94.91,
      "score": 71.93
     },
     "awt": {
      "raw": 690.807,
      "sd": 160.889,
      "score": 66.26
     },
     "aql": {
      "raw": 1626.051,
      "sd": 313.143,
      "score": 62.65
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1358.078,
      "sd": 41.415,
      "score": 72.52
     },
     "awt": {
      "raw": 987.298,
      "sd": 50.809,
      "score": 66.34
     },
     "aql": {
      "raw": 2974.987,
      "sd": 133.421,
      "score": 58.73
     }
    }
   },
   "cost": {
    "gpu_seconds": 235.2,
    "wall_seconds": 80.3,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 80.3,
     "jinan-2": 70.3,
     "jinan-3": 70.3,
     "hangzhou-1": 70.3,
     "hangzhou-2": 100.4,
     "newyork-1": 562.3,
     "newyork-2": 692.8
    }
   },
   "rank": 2
  },
  {
   "id": "mplight",
   "name": "MPLight",
   "mode": "baseline",
   "score": 77.18,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 340.54,
      "sd": 0.87,
      "score": 95.47
     },
     "awt": {
      "raw": 82.902,
      "sd": 0.56,
      "score": 87.74
     },
     "aql": {
      "raw": 144.694,
      "sd": 0.989,
      "score": 86.07
     }
    },
    "jinan-2": {
     "att": {
      "raw": 330.773,
      "sd": 1.267,
      "score": 94.63
     },
     "awt": {
      "raw": 68.241,
      "sd": 0.418,
      "score": 84.16
     },
     "aql": {
      "raw": 82.578,
      "sd": 0.506,
      "score": 82.94
     }
    },
    "jinan-3": {
     "att": {
      "raw": 323.942,
      "sd": 0.397,
      "score": 94.67
     },
     "awt": {
      "raw": 71.478,
      "sd": 0.596,
      "score": 85.05
     },
     "aql": {
      "raw": 108.875,
      "sd": 0.918,
      "score": 83.49
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 370.624,
      "sd": 1.083,
      "score": 94.54
     },
     "awt": {
      "raw": 55.016,
      "sd": 1.262,
      "score": 80.42
     },
     "aql": {
      "raw": 45.522,
      "sd": 1.045,
      "score": 78.52
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 399.868,
      "sd": 4.223,
      "score": 92.71
     },
     "awt": {
      "raw": 96.85,
      "sd": 5.575,
      "score": 84.7
     },
     "aql": {
      "raw": 157.4,
      "sd": 7.718,
      "score": 81.79
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1212.538,
      "sd": 14.582,
      "score": 61.72
     },
     "awt": {
      "raw": 858.766,
      "sd": 16.448,
      "score": 51.95
     },
     "aql": {
      "raw": 1903.423,
      "sd": 15.803,
      "score": 49.42
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1529.485,
      "sd": 18.051,
      "score": 53.57
     },
     "awt": {
      "raw": 1209.333,
      "sd": 19.958,
      "score": 47.42
     },
     "aql": {
      "raw": 3183.4,
      "sd": 31.798,
      "score": 49.88
     }
    }
   },
   "cost": {
    "gpu_seconds": 275.5,
    "wall_seconds": 110.4,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 110.4,
     "jinan-2": 90.4,
     "jinan-3": 100.4,
     "hangzhou-1": 90.4,
     "hangzhou-2": 120.5,
     "newyork-1": 652.8,
     "newyork-2": 763.4
    }
   },
   "rank": 3
  },
  {
   "id": "webster",
   "name": "Webster",
   "mode": "baseline",
   "score": 74.31,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 387.89,
      "sd": 2.628,
      "score": 87.07
     },
     "awt": {
      "raw": 122.631,
      "sd": 2.377,
      "score": 75.41
     },
     "aql": {
      "raw": 214.125,
      "sd": 4.208,
      "score": 72.09
     }
    },
    "jinan-2": {
     "att": {
      "raw": 332.44,
      "sd": 1.375,
      "score": 94.33
     },
     "awt": {
      "raw": 66.138,
      "sd": 0.907,
      "score": 85.03
     },
     "aql": {
      "raw": 80.02,
      "sd": 1.102,
      "score": 83.87
     }
    },
    "jinan-3": {
     "att": {
      "raw": 337.041,
      "sd": 3.073,
      "score": 92.17
     },
     "awt": {
      "raw": 79.654,
      "sd": 3.082,
      "score": 81.88
     },
     "aql": {
      "raw": 121.35,
      "sd": 4.696,
      "score": 79.99
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 377.122,
      "sd": 0.782,
      "score": 93.39
     },
     "awt": {
      "raw": 57.12,
      "sd": 0.45,
      "score": 79.48
     },
     "aql": {
      "raw": 47.262,
      "sd": 0.374,
      "score": 77.49
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 414.172,
      "sd": 0.835,
      "score": 89.37
     },
     "awt": {
      "raw": 111.349,
      "sd": 2.355,
      "score": 79.4
     },
     "aql": {
      "raw": 175.844,
      "sd": 3.881,
      "score": 76.58
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1207.553,
      "sd": 1.325,
      "score": 62.22
     },
     "awt": {
      "raw": 831.754,
      "sd": 4.606,
      "score": 54.05
     },
     "aql": {
      "raw": 2016.173,
      "sd": 15.763,
      "score": 44.59
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1489.483,
      "sd": 1.334,
      "score": 57.79
     },
     "awt": {
      "raw": 1147.296,
      "sd": 3.812,
      "score": 52.33
     },
     "aql": {
      "raw": 3379.361,
      "sd": 16.696,
      "score": 42.06
     }
    }
   },
   "cost": {
    "gpu_seconds": 234.7,
    "wall_seconds": 80.1,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 90.2,
     "jinan-2": 60.1,
     "jinan-3": 70.1,
     "hangzhou-1": 50.1,
     "hangzhou-2": 80.1,
     "newyork-1": 560.8,
     "newyork-2": 731.6
    }
   },
   "rank": 4
  },
  {
   "id": "maxpressure",
   "name": "MaxPressure",
   "mode": "baseline",
   "score": 73.81,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 345.208,
      "sd": 0.64,
      "score": 94.59
     },
     "awt": {
      "raw": 88.23,
      "sd": 0.611,
      "score": 85.78
     },
     "aql": {
      "raw": 154.033,
      "sd": 1.073,
      "score": 83.84
     }
    },
    "jinan-2": {
     "att": {
      "raw": 329.334,
      "sd": 1.192,
      "score": 94.89
     },
     "awt": {
      "raw": 67.032,
      "sd": 0.66,
      "score": 84.65
     },
     "aql": {
      "raw": 81.141,
      "sd": 0.797,
      "score": 83.46
     }
    },
    "jinan-3": {
     "att": {
      "raw": 323.672,
      "sd": 0.954,
      "score": 94.72
     },
     "awt": {
      "raw": 71.833,
      "sd": 0.751,
      "score": 84.9
     },
     "aql": {
      "raw": 109.436,
      "sd": 1.14,
      "score": 83.32
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 383.547,
      "sd": 2.952,
      "score": 92.26
     },
     "awt": {
      "raw": 69.948,
      "sd": 2.309,
      "score": 74.41
     },
     "aql": {
      "raw": 57.907,
      "sd": 1.917,
      "score": 71.93
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 435.657,
      "sd": 4.116,
      "score": 84.56
     },
     "awt": {
      "raw": 140.697,
      "sd": 4.36,
      "score": 70.52
     },
     "aql": {
      "raw": 244.88,
      "sd": 4.332,
      "score": 61.01
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1188.417,
      "sd": 10.025,
      "score": 64.15
     },
     "awt": {
      "raw": 806.233,
      "sd": 11.012,
      "score": 56.1
     },
     "aql": {
      "raw": 2058.528,
      "sd": 18.782,
      "score": 42.85
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1506.699,
      "sd": 4.146,
      "score": 55.96
     },
     "awt": {
      "raw": 1149.194,
      "sd": 3.921,
      "score": 52.18
     },
     "aql": {
      "raw": 3596.211,
      "sd": 6.996,
      "score": 33.93
     }
    }
   },
   "cost": {
    "gpu_seconds": 212.5,
    "wall_seconds": 61.4,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 61.4,
     "jinan-2": 47.9,
     "jinan-3": 52.7,
     "hangzhou-1": 46.5,
     "hangzhou-2": 79.7,
     "newyork-1": 528.4,
     "newyork-2": 670.8
    }
   },
   "rank": 5
  },
  {
   "id": "advanceddqn",
   "name": "AdvancedDQN",
   "mode": "baseline",
   "score": 67.2,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 342.412,
      "sd": 2.13,
      "score": 95.11
     },
     "awt": {
      "raw": 81.503,
      "sd": 2.249,
      "score": 88.27
     },
     "aql": {
      "raw": 142.25,
      "sd": 3.924,
      "score": 86.68
     }
    },
    "jinan-2": {
     "att": {
      "raw": 331.799,
      "sd": 0.863,
      "score": 94.44
     },
     "awt": {
      "raw": 67.786,
      "sd": 1.225,
      "score": 84.35
     },
     "aql": {
      "raw": 82.027,
      "sd": 1.476,
      "score": 83.14
     }
    },
    "jinan-3": {
     "att": {
      "raw": 325.1,
      "sd": 2.724,
      "score": 94.44
     },
     "awt": {
      "raw": 70.372,
      "sd": 2.521,
      "score": 85.5
     },
     "aql": {
      "raw": 107.195,
      "sd": 3.854,
      "score": 83.99
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 456.662,
      "sd": 56.979,
      "score": 80.68
     },
     "awt": {
      "raw": 147.226,
      "sd": 64.386,
      "score": 55.78
     },
     "aql": {
      "raw": 121.905,
      "sd": 53.345,
      "score": 51.53
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 471.696,
      "sd": 18.97,
      "score": 77.0
     },
     "awt": {
      "raw": 187.328,
      "sd": 20.681,
      "score": 59.65
     },
     "aql": {
      "raw": 312.593,
      "sd": 34.255,
      "score": 49.52
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1381.377,
      "sd": 24.307,
      "score": 45.95
     },
     "awt": {
      "raw": 1046.959,
      "sd": 34.777,
      "score": 38.92
     },
     "aql": {
      "raw": 2351.772,
      "sd": 83.735,
      "score": 31.66
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1582.481,
      "sd": 5.878,
      "score": 48.13
     },
     "awt": {
      "raw": 1282.804,
      "sd": 10.861,
      "score": 41.92
     },
     "aql": {
      "raw": 3577.247,
      "sd": 26.333,
      "score": 34.62
     }
    }
   },
   "cost": {
    "gpu_seconds": 279.8,
    "wall_seconds": 100.4,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 100.4,
     "jinan-2": 90.4,
     "jinan-3": 90.4,
     "hangzhou-1": 100.4,
     "hangzhou-2": 120.5,
     "newyork-1": 662.8,
     "newyork-2": 793.4
    }
   },
   "rank": 6
  },
  {
   "id": "maxpressure-strict",
   "name": "MaxPressure (strict)",
   "mode": "baseline",
   "score": 63.41,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 357.765,
      "sd": 6.824,
      "score": 92.28
     },
     "awt": {
      "raw": 94.853,
      "sd": 6.064,
      "score": 83.5
     },
     "aql": {
      "raw": 165.58,
      "sd": 10.613,
      "score": 81.26
     }
    },
    "jinan-2": {
     "att": {
      "raw": 333.004,
      "sd": 0.367,
      "score": 94.22
     },
     "awt": {
      "raw": 68.561,
      "sd": 0.461,
      "score": 84.03
     },
     "aql": {
      "raw": 82.951,
      "sd": 0.567,
      "score": 82.81
     }
    },
    "jinan-3": {
     "att": {
      "raw": 323.883,
      "sd": 5.295,
      "score": 94.68
     },
     "awt": {
      "raw": 68.353,
      "sd": 5.335,
      "score": 86.36
     },
     "aql": {
      "raw": 104.098,
      "sd": 8.135,
      "score": 84.94
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 448.713,
      "sd": 38.875,
      "score": 81.85
     },
     "awt": {
      "raw": 138.846,
      "sd": 42.876,
      "score": 57.25
     },
     "aql": {
      "raw": 114.966,
      "sd": 35.527,
      "score": 53.13
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 437.72,
      "sd": 10.625,
      "score": 84.11
     },
     "awt": {
      "raw": 141.136,
      "sd": 11.878,
      "score": 70.4
     },
     "aql": {
      "raw": 245.35,
      "sd": 20.658,
      "score": 60.92
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1578.97,
      "sd": 2.072,
      "score": 29.78
     },
     "awt": {
      "raw": 1253.224,
      "sd": 2.814,
      "score": 27.1
     },
     "aql": {
      "raw": 2953.641,
      "sd": 10.074,
      "score": 12.53
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1791.572,
      "sd": 4.317,
      "score": 28.34
     },
     "awt": {
      "raw": 1483.53,
      "sd": 4.26,
      "score": 28.36
     },
     "aql": {
      "raw": 4194.598,
      "sd": 17.532,
      "score": 13.79
     }
    }
   },
   "cost": {
    "gpu_seconds": 240.4,
    "wall_seconds": 70.1,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 70.1,
     "jinan-2": 60.1,
     "jinan-3": 60.1,
     "hangzhou-1": 60.1,
     "hangzhou-2": 90.1,
     "newyork-1": 600.9,
     "newyork-2": 741.1
    }
   },
   "rank": 7
  },
  {
   "id": "attendlight",
   "name": "AttendLight",
   "mode": "baseline",
   "score": 62.59,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 388.479,
      "sd": 6.777,
      "score": 86.97
     },
     "awt": {
      "raw": 128.884,
      "sd": 6.593,
      "score": 73.85
     },
     "aql": {
      "raw": 225.074,
      "sd": 11.524,
      "score": 70.31
     }
    },
    "jinan-2": {
     "att": {
      "raw": 356.454,
      "sd": 2.896,
      "score": 90.12
     },
     "awt": {
      "raw": 92.926,
      "sd": 1.54,
      "score": 75.63
     },
     "aql": {
      "raw": 112.501,
      "sd": 1.868,
      "score": 73.76
     }
    },
    "jinan-3": {
     "att": {
      "raw": 354.896,
      "sd": 13.059,
      "score": 88.91
     },
     "awt": {
      "raw": 100.88,
      "sd": 13.243,
      "score": 74.96
     },
     "aql": {
      "raw": 153.733,
      "sd": 20.203,
      "score": 72.37
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 432.802,
      "sd": 7.778,
      "score": 84.24
     },
     "awt": {
      "raw": 120.542,
      "sd": 10.624,
      "score": 60.79
     },
     "aql": {
      "raw": 99.807,
      "sd": 8.811,
      "score": 57.01
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 436.167,
      "sd": 13.718,
      "score": 84.45
     },
     "awt": {
      "raw": 146.205,
      "sd": 9.45,
      "score": 69.06
     },
     "aql": {
      "raw": 236.652,
      "sd": 15.895,
      "score": 62.61
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1442.588,
      "sd": 8.96,
      "score": 40.71
     },
     "awt": {
      "raw": 1122.097,
      "sd": 14.07,
      "score": 34.37
     },
     "aql": {
      "raw": 2608.725,
      "sd": 36.006,
      "score": 22.96
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1697.803,
      "sd": 8.629,
      "score": 36.92
     },
     "awt": {
      "raw": 1410.197,
      "sd": 15.371,
      "score": 33.09
     },
     "aql": {
      "raw": 3959.72,
      "sd": 10.858,
      "score": 21.33
     }
    }
   },
   "cost": {
    "gpu_seconds": 295.6,
    "wall_seconds": 110.5,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 110.5,
     "jinan-2": 100.4,
     "jinan-3": 100.5,
     "hangzhou-1": 90.3,
     "hangzhou-2": 120.5,
     "newyork-1": 703.2,
     "newyork-2": 843.7
    }
   },
   "rank": 8
  },
  {
   "id": "presslight",
   "name": "PressLight",
   "mode": "baseline",
   "score": 58.87,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 361.92,
      "sd": 3.03,
      "score": 91.54
     },
     "awt": {
      "raw": 97.119,
      "sd": 2.847,
      "score": 82.75
     },
     "aql": {
      "raw": 169.552,
      "sd": 4.977,
      "score": 80.42
     }
    },
    "jinan-2": {
     "att": {
      "raw": 342.606,
      "sd": 2.06,
      "score": 92.51
     },
     "awt": {
      "raw": 76.166,
      "sd": 1.415,
      "score": 81.13
     },
     "aql": {
      "raw": 92.203,
      "sd": 1.713,
      "score": 79.67
     }
    },
    "jinan-3": {
     "att": {
      "raw": 334.056,
      "sd": 2.701,
      "score": 92.73
     },
     "awt": {
      "raw": 76.554,
      "sd": 1.951,
      "score": 83.04
     },
     "aql": {
      "raw": 116.608,
      "sd": 2.986,
      "score": 81.28
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 539.737,
      "sd": 51.667,
      "score": 69.58
     },
     "awt": {
      "raw": 219.838,
      "sd": 49.491,
      "score": 45.74
     },
     "aql": {
      "raw": 178.23,
      "sd": 39.301,
      "score": 41.12
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 526.162,
      "sd": 21.431,
      "score": 66.6
     },
     "awt": {
      "raw": 249.19,
      "sd": 25.055,
      "score": 48.81
     },
     "aql": {
      "raw": 349.37,
      "sd": 23.173,
      "score": 44.29
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1584.574,
      "sd": 5.982,
      "score": 29.35
     },
     "awt": {
      "raw": 1286.635,
      "sd": 2.51,
      "score": 25.37
     },
     "aql": {
      "raw": 2776.221,
      "sd": 13.898,
      "score": 17.73
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1735.46,
      "sd": 10.437,
      "score": 33.42
     },
     "awt": {
      "raw": 1453.792,
      "sd": 13.792,
      "score": 30.25
     },
     "aql": {
      "raw": 4032.397,
      "sd": 33.106,
      "score": 18.95
     }
    }
   },
   "cost": {
    "gpu_seconds": 292.6,
    "wall_seconds": 110.5,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 110.5,
     "jinan-2": 90.3,
     "jinan-3": 100.4,
     "hangzhou-1": 100.4,
     "hangzhou-2": 120.5,
     "newyork-1": 692.8,
     "newyork-2": 833.3
    }
   },
   "rank": 9
  },
  {
   "id": "fixedtime",
   "name": "FixedTime",
   "mode": "baseline",
   "score": 54.39,
   "cells": {
    "jinan-1": {
     "att": {
      "raw": 505.407,
      "sd": 0.608,
      "score": 69.99
     },
     "awt": {
      "raw": 219.716,
      "sd": 0.153,
      "score": 57.06
     },
     "aql": {
      "raw": 363.524,
      "sd": 0.305,
      "score": 53.21
     }
    },
    "jinan-2": {
     "att": {
      "raw": 429.692,
      "sd": 1.949,
      "score": 78.85
     },
     "awt": {
      "raw": 147.018,
      "sd": 2.061,
      "score": 62.95
     },
     "aql": {
      "raw": 178.044,
      "sd": 2.44,
      "score": 60.13
     }
    },
    "jinan-3": {
     "att": {
      "raw": 456.551,
      "sd": 1.359,
      "score": 73.01
     },
     "awt": {
      "raw": 180.123,
      "sd": 1.41,
      "score": 57.99
     },
     "aql": {
      "raw": 264.91,
      "sd": 2.2,
      "score": 54.82
     }
    },
    "hangzhou-1": {
     "att": {
      "raw": 559.954,
      "sd": 4.683,
      "score": 67.14
     },
     "awt": {
      "raw": 201.913,
      "sd": 8.986,
      "score": 47.87
     },
     "aql": {
      "raw": 158.479,
      "sd": 6.917,
      "score": 44.34
     }
    },
    "hangzhou-2": {
     "att": {
      "raw": 478.947,
      "sd": 4.105,
      "score": 75.55
     },
     "awt": {
      "raw": 171.561,
      "sd": 2.463,
      "score": 62.99
     },
     "aql": {
      "raw": 241.806,
      "sd": 3.202,
      "score": 61.6
     }
    },
    "newyork-1": {
     "att": {
      "raw": 1430.829,
      "sd": 1.334,
      "score": 41.7
     },
     "awt": {
      "raw": 1111.269,
      "sd": 2.543,
      "score": 35.0
     },
     "aql": {
      "raw": 2499.199,
      "sd": 7.413,
      "score": 26.56
     }
    },
    "newyork-2": {
     "att": {
      "raw": 1644.533,
      "sd": 5.014,
      "score": 42.0
     },
     "awt": {
      "raw": 1333.247,
      "sd": 5.376,
      "score": 38.33
     },
     "aql": {
      "raw": 3676.934,
      "sd": 11.726,
      "score": 31.02
     }
    }
   },
   "cost": {
    "gpu_seconds": 247.5,
    "wall_seconds": 80.1,
    "gpus": 1,
    "hosted": false,
    "basis": "wall clock x 1 GPU",
    "by_flow": {
     "jinan-1": 90.1,
     "jinan-2": 70.1,
     "jinan-3": 80.1,
     "hangzhou-1": 60.1,
     "hangzhou-2": 80.1,
     "newyork-1": 600.7,
     "newyork-2": 751.0
    }
   },
   "rank": 10
  }
 ]
};
