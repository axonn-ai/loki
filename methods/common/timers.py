import torch
from collections import defaultdict

class Timers():
    def __init__(self):
        self.timers = defaultdict(list)
        self.curr_index = defaultdict(int)

    def start(self, key):
        index = self.curr_index[key]
        timers = self.timers[key]
        assert index == len(timers) or index < len(timers)
        if index == len(timers):
            self.timers[key].append([torch.cuda.Event(enable_timing=True) for _ in range(2)])
        self.timers[key][index][0].record()


    def stop(self, key):
        index = self.curr_index[key]
        self.timers[key][index][1].record()
        self.curr_index[key] += 1

    def get_times(self, skip_first_n=0):
        torch.cuda.synchronize()
        total_times = defaultdict(float)
        for key in self.timers:
            for i, events in enumerate(self.timers[key]):
                start_event, end_event = events
                time_elapsed = start_event.elapsed_time(end_event) / 1000
                if i < skip_first_n:
                    continue
                total_times[key] += time_elapsed
            self.curr_index[key] = 0
        return total_times
