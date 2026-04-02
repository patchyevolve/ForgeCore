import builtins
from unittest.mock import patch

from forge import ForgeREPL
from core.patch_intent import Operation, PatchIntent


TASK = "Create file main.cpp with a complete scientific calculator in C++. It should be a console app with a menu for add, subtract, multiply, divide, power, square root, sine, cosine, tangent, logarithm, natural log, and exit. Use clean functions, input validation, divide-by-zero handling, invalid domain handling, and clear formatted output."

CODE = """#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>

namespace {
constexpr double kPi = 3.14159265358979323846;

void clearInput() {
    std::cin.clear();
    std::cin.ignore(std::numeric_limits<std::streamsize>::max(), '\\n');
}

double readNumber(const std::string& prompt) {
    double value = 0.0;
    while (true) {
        std::cout << prompt;
        if (std::cin >> value) {
            clearInput();
            return value;
        }
        std::cout << "Invalid input. Please enter a number.\\n";
        clearInput();
    }
}

int readChoice() {
    int choice = -1;
    while (true) {
        std::cout << "\\nScientific Calculator\\n";
        std::cout << "1. Add\\n";
        std::cout << "2. Subtract\\n";
        std::cout << "3. Multiply\\n";
        std::cout << "4. Divide\\n";
        std::cout << "5. Power\\n";
        std::cout << "6. Square Root\\n";
        std::cout << "7. Sine\\n";
        std::cout << "8. Cosine\\n";
        std::cout << "9. Tangent\\n";
        std::cout << "10. Logarithm (base 10)\\n";
        std::cout << "11. Natural Log\\n";
        std::cout << "0. Exit\\n";
        std::cout << "Choose an option: ";
        if (std::cin >> choice && choice >= 0 && choice <= 11) {
            clearInput();
            return choice;
        }
        std::cout << "Invalid choice. Please select 0 to 11.\\n";
        clearInput();
    }
}

double toRadians(double degrees) {
    return degrees * kPi / 180.0;
}

void showResult(double value) {
    std::cout << std::fixed << std::setprecision(6);
    std::cout << "Result: " << value << "\\n";
}

void handleBinaryOperation(int choice) {
    const double left = readNumber("Enter the first number: ");
    const double right = readNumber("Enter the second number: ");

    switch (choice) {
        case 1:
            showResult(left + right);
            break;
        case 2:
            showResult(left - right);
            break;
        case 3:
            showResult(left * right);
            break;
        case 4:
            if (right == 0.0) {
                std::cout << "Error: Division by zero is not allowed.\\n";
                return;
            }
            showResult(left / right);
            break;
        case 5:
            showResult(std::pow(left, right));
            break;
        default:
            break;
    }
}

void handleUnaryOperation(int choice) {
    const double value = readNumber("Enter the number: ");

    switch (choice) {
        case 6:
            if (value < 0.0) {
                std::cout << "Error: Square root requires a non-negative number.\\n";
                return;
            }
            showResult(std::sqrt(value));
            break;
        case 7:
            showResult(std::sin(toRadians(value)));
            break;
        case 8:
            showResult(std::cos(toRadians(value)));
            break;
        case 9:
            showResult(std::tan(toRadians(value)));
            break;
        case 10:
            if (value <= 0.0) {
                std::cout << "Error: Logarithm requires a positive number.\\n";
                return;
            }
            showResult(std::log10(value));
            break;
        case 11:
            if (value <= 0.0) {
                std::cout << "Error: Natural log requires a positive number.\\n";
                return;
            }
            showResult(std::log(value));
            break;
        default:
            break;
    }
}

}

int main() {
    std::cout << "Welcome to the Scientific Calculator\\n";
    while (true) {
        const int choice = readChoice();
        if (choice == 0) {
            std::cout << "Goodbye!\\n";
            return 0;
        }

        if (choice >= 1 && choice <= 5) {
            handleBinaryOperation(choice);
        } else {
            handleUnaryOperation(choice);
        }
    }
}
"""


class DemoPlanner:
    def __init__(self, context_manager):
        self.context_manager = context_manager

    def generate_intent(self, task_description, error_context=None, iteration=1, previous_intent=None):
        return PatchIntent.single_file(
            target_file="main.cpp",
            operation=Operation.CREATE_FILE,
            payload={"content": CODE},
            description="Create a complete C++ scientific calculator console application in main.cpp"
        )


class DemoCritic:
    def review_intent(self, intent, context_manager, task_desc):
        return True, "Approved for demonstration"

    def review_result(self, intent, original, modified, task_desc):
        return True, "Result looks valid"


def main():
    repl = ForgeREPL(r"D:\\op")
    if not repl.initialize():
        raise SystemExit(1)

    planner = DemoPlanner(repl.controller.planner.context_manager)
    critic = DemoCritic()

    repl.controller.planner = planner
    repl.controller.critic = critic
    repl.controller.execution_engine.planner = planner
    repl.controller.execution_engine.critic = critic
    repl.session.planner = planner
    repl.session.critic = critic

    with patch.object(builtins, "input", side_effect=["y"]):
        repl.execute_task(TASK)


if __name__ == "__main__":
    main()
