using System;
using System.Windows.Input;

namespace cs_wpf_anycpu
{
    public class relay_cmd : ICommand{
        readonly Action<object> _execute;
        readonly Predicate<object> _can_execute;
        public relay_cmd(Action<object> execute) : this(execute, null) {}
        public relay_cmd(Action<object> execute, Predicate<object> can_execute)
        {
            if (execute == null)
                throw new ArgumentNullException("execute");
            _execute = execute;
            _can_execute = can_execute;
        }
        public bool can_execute(object param)
        {
            return _can_execute == null ? true : _can_execute(param);
        }
        public bool CanExecute(object parameter)
        {
            return _can_execute == null ? true : _can_execute(parameter);
        }
        public event EventHandler CanExecuteChanged
        {
            add { CommandManager.RequerySuggested += value; }
            remove { CommandManager.RequerySuggested -= value; }
        }
        public void Execute(object parameter)
        {
            _execute(parameter);
        }
    }
}
