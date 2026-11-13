package cn.guga.ledger;

import android.app.job.*;

/** Runs when MediaStore images change (WATCH_JOB) or on demand (RUN_JOB); no long-lived service. */
public class CaptureJob extends JobService {
    @Override public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try { Capture.scan(this); Capture.processPending(this); }
            finally {
                jobFinished(params,false);
                // Content-trigger jobs fire once; watch again for the next screenshot.
                if (params.getJobId()==Capture.WATCH_JOB) Capture.schedule(this);
            }
        },"ledger-capture").start();
        return true;
    }
    @Override public boolean onStopJob(JobParameters params) { return true; }
}
