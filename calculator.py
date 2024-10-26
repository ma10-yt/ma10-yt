print("MEHRAN's CALCULATOR")
while True:
    while True:
        user_input = input("Enter first number: ")
        if user_input.replace('.','', 1).isdigit():
          num1 = float(user_input)
          break
        else:
            print("Invalid input. Please enter a number.")
    
    while True:
        user_input = input("Enter second number: ")
        if user_input.replace('.', '', 1).isdigit():
            num2 = float(user_input)
            break
        else:
            print("Invalid input. Please enter a number.")
    
    print("press + for addition \npress - for subtraction \npress x for multiplication \npress / for division \npress ^ for exponential")
    while True:
        choice = input("Enter your choice: ")
        if choice == '+':   
          print("Answer = ",num1 + num2)
          break
        elif choice == '-':
          print("Answer = ",num1 - num2)
          break
        elif choice == 'x':
          print("Answer = ",num1 * num2)
          break
        elif choice == '/':
          if num2 != 0:
              print("Answer = ",num1 / num2)
              break
          else:
              print("Error! Division by zero is not allowed.")
        elif choice == '^':
          print("Answer = ",num1 ** num2)
          break
        else:
          print ("Invalid input 'enter given values only'")
    print("CALCULATOR is ready for new calculations")