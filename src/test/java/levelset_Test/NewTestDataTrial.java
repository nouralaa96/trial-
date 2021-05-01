package levelset_Test;

import java.util.concurrent.TimeUnit;

import org.junit.AfterClass;
import org.openqa.selenium.By;
import org.openqa.selenium.By.ByName;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.testng.Assert;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeClass;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.DataProvider;
import org.testng.annotations.Test;

import actions.BrowserActions;
import actions.UIActions;
import io.github.bonigarcia.wdm.WebDriverManager;
import levelset_Main.Levelset_HomePage;

public class NewTestDataTrial { 
	
 Test_Class setupandNavigating= new Test_Class() ;
	  WebDriver driver ;
	 //  BrowserActions action ;
	   Levelset_HomePage homepage ; 
	   
	  @BeforeMethod
	   public void setup () {
		 driver = setupandNavigating.Setup();  // setup class from Test_Class 
		    
		    new UIActions().click(By.xpath("//a[normalize-space()='Sign in']"));  //click on sgin in 
		    new UIActions().click(By.linkText("Signup"));   // click on signup 
	  } 
	
	// data provider 
	  @DataProvider(name="signup_provider")
	  public Object [] [] getdatafrom_provider() {
		  
			return new Object [] [] {
				{"nouralaa1996@yahoo.com ","Nour123456"},   // first testcase each row represent testcase
				{"kjfjfkka@hotmail.com","Kk123456"}         // second testcase
				
			} ; 
	  }
	  
	  
	  By Email = By.name("user_email") ;  
	  By Password = By.id("input-pass");
	  
  @Test(dataProvider="signup_provider")     // to use data in this test.
  public void testSignup_form(String email , String password) { 
	 //  driver.findElement(Email).clear(); 
	 //  driver.findElement(Password).clear(); 
	   
	   driver.findElement(Email).sendKeys(email); 
	   driver.findElement(Password).sendKeys(password); 
	   
	    //    JavascriptExecutor for scrolldown 
	   WebElement Element = driver.findElement((By.xpath("//input[@id='checkbox-agree']")));
	   
	   JavascriptExecutor js = (JavascriptExecutor) driver; 
	   
	   js.executeScript("arguments[0].scrollIntoView();", Element); // first parameter is string with javascrpit code
	                                                                // second is the  object argument.
	   js.executeScript("arguments[0].click();", Element); // to click on checkbox
	 //  new UIActions().click(By.xpath("//input[@id='checkbox-agree']")); // path for checkbox  
	   
	    driver.manage().timeouts().implicitlyWait(10,TimeUnit.SECONDS) ;
	   // for submiting 
	  //   new UIActions().click(By.xpath("//button[normalize-space()='Get Started']")); 
	
	     new UIActions().checkclickable_Button(By.xpath("//button[normalize-space()='Get Started']")); 

	   
  } 
  
  @AfterMethod
  public void aftertest() {
	  //action.closeDriver();
	  driver.quit();
	  
  }
  
  
}
