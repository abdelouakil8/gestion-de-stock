import sys

import win32api
import win32event
import win32job
import win32process


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_constrained.py <command...>")
        sys.exit(1)
        
    cmd = sys.argv[1:]
    
    # Create a job object
    hJob = win32job.CreateJobObject(None, "")
    
    # Set Extended Limits (2GB memory cap)
    limits = win32job.QueryInformationJobObject(hJob, win32job.JobObjectExtendedLimitInformation)
    limits['ProcessMemoryLimit'] = 2 * 1024 * 1024 * 1024 # 2 GB
    limits['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
    win32job.SetInformationJobObject(hJob, win32job.JobObjectExtendedLimitInformation, limits)
    
    # CPU rate control not available in pywin32 win32job, skipping. in a suspended state
    si = win32process.STARTUPINFO()
    
    # cmd needs to be a single string for CreateProcess if we pass None for lpApplicationName
    # Let's use the first arg as app name or just pass None and full cmd line
    cmd_line = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    print(f"Running constrained: {cmd_line}")
    pi = win32process.CreateProcess(
        None, 
        cmd_line, 
        None, 
        None, 
        True, 
        win32process.CREATE_SUSPENDED, 
        None, 
        None, 
        si
    )
    
    hProcess, hThread, dwProcessId, dwThreadId = pi
    
    # Assign process to job
    win32job.AssignProcessToJobObject(hJob, hProcess)
    
    # Resume the thread
    win32process.ResumeThread(hThread)
    
    # Wait for the process to finish
    win32event.WaitForSingleObject(hProcess, win32event.INFINITE)
    
    # Get exit code
    exit_code = win32process.GetExitCodeProcess(hProcess)
    win32api.CloseHandle(hThread)
    win32api.CloseHandle(hProcess)
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
